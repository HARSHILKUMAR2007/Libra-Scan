"""End-to-end book processing pipeline chaining preprocessing, OCR, and LLM."""

import concurrent.futures
import hashlib
import logging
from typing import Callable, Optional

from app.schemas.book import BookDetails, BookResult, ImageDimensions, ImageMeta, ProcessedField
from app.schemas.ocr import OcrLine, OcrResult
from app.services.geometry import merge_boxes_for_field
from app.services.isbn import extract_isbns_from_text, validate_and_sanitize_isbns
from app.services.llm import build_prompt_ocr_block, extract_book
from app.services.ocr import run_ocr
from app.services.preprocess import preprocess

logger = logging.getLogger(__name__)
_PIPELINE_CACHE: dict[str, BookResult] = {}


def compute_combined_hash(front_bytes: bytes, back_bytes: Optional[bytes]) -> str:
    """Compute SHA-256 cache key from front and optional back image hashes."""
    f_hash = hashlib.sha256(front_bytes).hexdigest()
    b_hash = hashlib.sha256(back_bytes).hexdigest() if back_bytes else ""
    return hashlib.sha256((f_hash + b_hash).encode("utf-8")).hexdigest()


def _assign_global_ids(front_res: OcrResult, back_res: Optional[OcrResult]) -> tuple[list[OcrLine], list[OcrLine]]:
    """Assign globally unique IDs top-to-bottom across front (0..N-1) and back (N..)."""
    f_lines = sorted(front_res.lines, key=lambda l: l.bbox[1])
    assigned_front = [
        OcrLine(id=i, text=l.text, polygon=l.polygon, bbox=l.bbox, confidence=l.confidence, image="front")
        for i, l in enumerate(f_lines)
    ]
    start_id = len(assigned_front)
    assigned_back: list[OcrLine] = []
    if back_res:
        b_lines = sorted(back_res.lines, key=lambda l: l.bbox[1])
        assigned_back = [
            OcrLine(id=start_id + i, text=l.text, polygon=l.polygon, bbox=l.bbox, confidence=l.confidence, image="back")
            for i, l in enumerate(b_lines)
        ]
    return assigned_front, assigned_back


def process_book_images(
    front_bytes: bytes,
    back_bytes: Optional[bytes] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> BookResult:
    """Process front and optional back book covers through preprocessing, OCR, and LLM."""
    combined_hash = compute_combined_hash(front_bytes, back_bytes)
    if combined_hash in _PIPELINE_CACHE:
        logger.info("Pipeline cache hit for combined hash: %s", combined_hash)
        return _PIPELINE_CACHE[combined_hash]

    if progress_callback:
        progress_callback("Preprocessing")

    f_hash = hashlib.sha256(front_bytes).hexdigest()
    b_hash = hashlib.sha256(back_bytes).hexdigest() if back_bytes else None

    f_proc, f_meta = preprocess(front_bytes)
    b_proc, b_meta = preprocess(back_bytes) if back_bytes else (None, None)

    if progress_callback:
        progress_callback("Reading text")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_future = executor.submit(run_ocr, f_proc)
        b_future = executor.submit(run_ocr, b_proc) if b_proc is not None else None
        f_ocr = f_future.result()
        b_ocr = b_future.result() if b_future else None

    front_lines, back_lines = _assign_global_ids(f_ocr, b_ocr)
    all_lines = front_lines + back_lines
    if not all_lines:
        raise ValueError("No text detected")
    lines_by_id = {line.id: line for line in all_lines}

    isbn_hint = ""
    if back_lines:
        b_text = " ".join(line.text for line in back_lines)
        found_10, found_13 = extract_isbns_from_text(b_text)
        found_all = found_13 + found_10
        if found_all:
            isbn_hint = found_all[0]

    prompt_ocr_block = build_prompt_ocr_block(front_lines, back_lines if back_bytes else None)
    if progress_callback:
        progress_callback("Extracting details")
    book_details = extract_book(prompt_ocr_block, isbn_hint=isbn_hint)
    raw_dict = book_details.model_dump()

    clean_v10, clean_v13, isbn_warnings = validate_and_sanitize_isbns(
        raw_dict["isbn10"].get("value"), raw_dict["isbn13"].get("value")
    )
    raw_dict["isbn10"]["value"], raw_dict["isbn13"]["value"] = clean_v10, clean_v13

    warnings = list(isbn_warnings)
    needs_review = bool(isbn_warnings)

    all_null = all(f_data.get("value") in (None, "", []) for f_data in raw_dict.values())
    if all_null:
        needs_review = True
        warnings.append("No details could be extracted")

    if b_hash and f_hash == b_hash:
        warnings.append("Front and back images are identical.")
        needs_review = True

    fields: dict[str, ProcessedField] = {}
    confidences: list[float] = []
    for name, f_data in raw_dict.items():
        val = f_data.get("value")
        conf = float(f_data.get("confidence", 0.0))
        valid_ids = [lid for lid in f_data.get("source_line_ids", []) if lid in lines_by_id]
        dropped = len(f_data.get("source_line_ids", [])) - len(valid_ids)
        if dropped > 0:
            logger.warning("Field '%s': dropped %d invalid source_line_ids", name, dropped)

        ref_texts = [f"[{i}]: {lines_by_id[i].text}" for i in valid_ids]
        logger.info("Field '%s' (%s) -> IDs %s: %s", name, val, valid_ids, ref_texts)

        boxes = merge_boxes_for_field(valid_ids, lines_by_id)
        for box in boxes:
            box_area = (box.bbox[2] - box.bbox[0]) * (box.bbox[3] - box.bbox[1])
            if box_area > 0.35:
                logger.warning("Field '%s' has suspiciously large box on %s (%.1f%%)", name, box.image, box_area * 100)
                msg = f"Field '{name}' has a suspiciously large box."
                if msg not in warnings:
                    warnings.append(msg)
                needs_review = True

        fields[name] = ProcessedField(value=val, confidence=conf, boxes=boxes)
        if val not in (None, "", []):
            confidences.append(conf)

    overall_conf = round(float(sum(confidences) / len(confidences)), 3) if confidences else 0.0
    if not fields.get("title", ProcessedField()).value:
        needs_review = True
        warnings.append("Title could not be extracted.")
    if not fields.get("authors", ProcessedField()).value:
        needs_review = True
        warnings.append("Authors could not be extracted.")

    for k in ["title", "authors", "isbn13", "isbn10", "publisher", "year"]:
        fe = fields.get(k)
        if fe and fe.value is not None and fe.confidence < 0.6:
            needs_review = True
            warnings.append(f"Confidence for '{k}' is below 0.60 ({fe.confidence:.2f}).")

    images = ImageDimensions(
        front=ImageMeta(width=f_meta["original_width"], height=f_meta["original_height"]),
        back=ImageMeta(width=b_meta["original_width"], height=b_meta["original_height"]) if b_meta else None,
    )
    result = BookResult(
        fields=fields,
        overall_confidence=overall_conf,
        needs_review=needs_review,
        warnings=warnings,
        ocr_lines=all_lines,
        images=images,
        image_hash=combined_hash,
    )
    _PIPELINE_CACHE[combined_hash] = result
    return result


def process_book_image(image_bytes: bytes) -> BookResult:
    """Backward-compatible single-image runner."""
    return process_book_images(image_bytes, None)

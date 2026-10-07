"""End-to-end book processing pipeline chaining preprocessing, OCR, and LLM."""

import concurrent.futures
import hashlib
import logging
from typing import Callable, Optional

from app.schemas.book import BookDetails, BookResult, ImageDimensions, ImageMeta, ProcessedField
from app.schemas.ocr import OcrLine, OcrResult
from app.services.geometry import merge_boxes_for_field
from app.services.guard import NotABookError, cap_lines, check_is_book, filter_lines, ground_and_validate
from app.services.isbn import clean_isbn, extract_isbns_from_text, validate_and_sanitize_isbns
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

    all_lines, guard_warnings, flagged = filter_lines(all_lines)
    check_is_book(all_lines)
    capped_lines = cap_lines(all_lines)
    lines_by_id = {line.id: line for line in all_lines}

    # Scan all OCR lines across front and back for ISBN patterns
    all_ocr_text = " ".join(line.text for line in all_lines)
    found_10, found_13 = extract_isbns_from_text(all_ocr_text)
    found_all = found_13 + found_10
    isbn_hint = found_all[0] if found_all else ""

    front_prompt_lines = [l for l in capped_lines if l.image == "front"]
    back_prompt_lines = [l for l in capped_lines if l.image == "back"]
    prompt_ocr_block = build_prompt_ocr_block(front_prompt_lines, back_prompt_lines if back_bytes else None)
    if progress_callback:
        progress_callback("Extracting details")
    book_details = extract_book(prompt_ocr_block, isbn_hint=isbn_hint)

    raw_dict_pre = book_details.model_dump()
    all_fields_null = all(
        f_data.get("value") in (None, "", [])
        for k, f_data in raw_dict_pre.items() if isinstance(f_data, dict) and "value" in f_data
    )
    if not book_details.is_book_cover and all_fields_null:
        raise NotABookError()

    book_details, gv_warnings = ground_and_validate(book_details, all_lines)
    raw_dict = book_details.model_dump()

    # Direct fallback: if LLM didn't capture or returned null for ISBNs, auto-populate from OCR regex
    curr_v10 = raw_dict["isbn10"].get("value")
    curr_v13 = raw_dict["isbn13"].get("value")
    if not curr_v13 and found_13:
        curr_v13 = found_13[0]
        raw_dict["isbn13"]["confidence"] = 0.95
    if not curr_v10 and found_10:
        curr_v10 = found_10[0]
        raw_dict["isbn10"]["confidence"] = 0.95

    clean_v10, clean_v13, isbn_warnings = validate_and_sanitize_isbns(curr_v10, curr_v13)
    raw_dict["isbn10"]["value"], raw_dict["isbn13"]["value"] = clean_v10, clean_v13

    if clean_v10 and not raw_dict["isbn10"].get("confidence"):
        raw_dict["isbn10"]["confidence"] = 0.92
    if clean_v13 and not raw_dict["isbn13"].get("confidence"):
        raw_dict["isbn13"]["confidence"] = 0.95

    # Auto-map bounding boxes to OCR lines where ISBN was located if source_line_ids is missing
    for isbn_key, isbn_val in [("isbn13", clean_v13), ("isbn10", clean_v10)]:
        if isbn_val and not raw_dict[isbn_key].get("source_line_ids"):
            clean_digits = clean_isbn(isbn_val)
            matching_ids = []
            for line in all_lines:
                line_clean = clean_isbn(line.text)
                if clean_digits in line_clean or (len(clean_digits) >= 8 and clean_digits[-8:] in line_clean):
                    matching_ids.append(line.id)
            if matching_ids:
                raw_dict[isbn_key]["source_line_ids"] = matching_ids

    warnings = list(guard_warnings) + list(gv_warnings) + list(isbn_warnings)
    needs_review = bool(flagged) or bool(gv_warnings) or bool(isbn_warnings)

    all_null = all(
        f_data.get("value") in (None, "", [])
        for k, f_data in raw_dict.items() if isinstance(f_data, dict) and "value" in f_data
    )
    if all_null:
        needs_review = True
        warnings.append("No details could be extracted")

    if b_hash and f_hash == b_hash:
        warnings.append("Front and back images are identical.")
        needs_review = True

    fields: dict[str, ProcessedField] = {}
    confidences: list[float] = []
    for name, f_data in raw_dict.items():
        if not isinstance(f_data, dict) or "value" not in f_data:
            continue
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

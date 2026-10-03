"""Unit tests for the end-to-end processing pipeline with front and back covers."""

from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest

from app.schemas.book import BookDetails, FieldValue
from app.schemas.ocr import OcrLine, OcrResult
from app.services.llm import build_prompt_ocr_block
from app.services.pipeline import (
    _PIPELINE_CACHE,
    _assign_global_ids,
    merge_boxes_for_field,
    process_book_images,
)


def _make_dummy_image(w: int, h: int, color: int = 120) -> bytes:
    arr = np.full((h, w, 3), color, dtype=np.uint8)
    _, encoded = cv2.imencode(".png", arr)
    return encoded.tobytes()


def test_assign_global_ids_and_unique_ids():
    front_lines = [
        OcrLine(id=99, text="Front Lower", polygon=[], bbox=(0.1, 0.4, 0.9, 0.5), confidence=0.9),
        OcrLine(id=88, text="Front Upper", polygon=[], bbox=(0.1, 0.1, 0.9, 0.2), confidence=0.95),
    ]
    back_lines = [
        OcrLine(id=77, text="Back Bottom", polygon=[], bbox=(0.2, 0.8, 0.8, 0.9), confidence=0.85),
        OcrLine(id=66, text="Back Top", polygon=[], bbox=(0.2, 0.05, 0.8, 0.15), confidence=0.88),
    ]
    f_res = OcrResult(lines=front_lines, width=100, height=200)
    b_res = OcrResult(lines=back_lines, width=300, height=400)

    f_assigned, b_assigned = _assign_global_ids(f_res, b_res)
    all_assigned = f_assigned + b_assigned
    ids = [l.id for l in all_assigned]

    assert ids == [0, 1, 2, 3]
    assert len(set(ids)) == 4
    assert f_assigned[0].text == "Front Upper" and f_assigned[0].image == "front"
    assert b_assigned[0].text == "Back Top" and b_assigned[0].image == "back"

    # Prompt block IDs must equal stored IDs
    block = build_prompt_ocr_block(f_assigned, b_assigned)
    for l in all_assigned:
        assert f"{l.id} | {l.text} |" in block


def test_neighbor_clustering_and_separate_boxes():
    lines_by_id = {
        # Front lines: 0 and 1 are neighbors (gap = 0.02, avg_h ~ 0.1)
        0: OcrLine(id=0, text="Title Line 1", polygon=[], bbox=(0.2, 0.1, 0.8, 0.2), confidence=0.9, image="front"),
        1: OcrLine(id=1, text="Title Line 2", polygon=[], bbox=(0.2, 0.22, 0.8, 0.32), confidence=0.9, image="front"),
        # Line 2 is far away on front (gap = 0.4 -> non-neighbor)
        2: OcrLine(id=2, text="Random Bottom Text", polygon=[], bbox=(0.2, 0.72, 0.8, 0.82), confidence=0.9, image="front"),
        # Line 3 is on back
        3: OcrLine(id=3, text="Back Blurb", polygon=[], bbox=(0.2, 0.1, 0.8, 0.2), confidence=0.9, image="back"),
    }

    boxes = merge_boxes_for_field([0, 1, 2, 3], lines_by_id)
    # Front should produce 2 boxes (cluster 0+1 and separate 2); back produces 1 box
    front_boxes = [b for b in boxes if b.image == "front"]
    back_boxes = [b for b in boxes if b.image == "back"]

    assert len(front_boxes) == 2
    assert len(back_boxes) == 1
    assert front_boxes[0].bbox == (0.2, 0.1, 0.8, 0.32)
    assert front_boxes[1].bbox == (0.2, 0.72, 0.8, 0.82)
    assert back_boxes[0].bbox == (0.2, 0.1, 0.8, 0.2)


def test_pipeline_drops_invalid_source_id_and_flags_identical_images():
    _PIPELINE_CACHE.clear()
    img_bytes = _make_dummy_image(120, 120, 80)

    fake_ocr = OcrResult(
        lines=[OcrLine(id=0, text="Only Line", polygon=[], bbox=(0.1, 0.1, 0.9, 0.2), confidence=0.9)],
        width=120,
        height=120,
    )
    # LLM returns a hallucinated source_line_id (999)
    fake_details = BookDetails(
        title=FieldValue(value="Valid Title", confidence=0.95, source_line_ids=[0, 999]),
        authors=FieldValue(value=["Some Author"], confidence=0.9, source_line_ids=[]),
    )

    with patch("app.services.pipeline.run_ocr", return_value=fake_ocr), \
         patch("app.services.pipeline.extract_book", return_value=fake_details):

        # Test identical front and back
        res = process_book_images(img_bytes, img_bytes)
        assert res.needs_review is True
        assert any("identical" in w.lower() for w in res.warnings)
        # Verify invalid id 999 was dropped, leaving only 1 valid box from line 0
        assert len(res.fields["title"].boxes) == 1


def test_pipeline_zero_ocr_lines_raises_no_text_detected():
    _PIPELINE_CACHE.clear()
    img_bytes = _make_dummy_image(120, 120, 80)
    empty_ocr = OcrResult(lines=[], width=120, height=120)

    with patch("app.services.pipeline.run_ocr", return_value=empty_ocr):
        with pytest.raises(ValueError, match="No text detected"):
            process_book_images(img_bytes, None)


def test_pipeline_all_null_llm_fields_sets_needs_review():
    _PIPELINE_CACHE.clear()
    img_bytes = _make_dummy_image(120, 120, 80)
    valid_ocr = OcrResult(
        lines=[OcrLine(id=0, text="Some random text", polygon=[], bbox=(0.1, 0.1, 0.9, 0.2), confidence=0.9)],
        width=120,
        height=120,
    )
    all_null_details = BookDetails()

    with patch("app.services.pipeline.run_ocr", return_value=valid_ocr), \
         patch("app.services.pipeline.extract_book", return_value=all_null_details):
        res = process_book_images(img_bytes, None)
        assert res.needs_review is True
        assert "No details could be extracted" in res.warnings


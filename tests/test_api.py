"""Integration tests for FastAPI book routes and front/back upload workflows."""

import io
from unittest.mock import patch
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.book import BookResult, FieldBox, ImageDimensions, ImageMeta, ProcessedField
from app.services.pipeline import _PIPELINE_CACHE

client = TestClient(app)


def _make_dummy_image(w: int, h: int, color: int = 120) -> bytes:
    arr = np.full((h, w, 3), color, dtype=np.uint8)
    _, enc = cv2.imencode(".png", arr)
    return enc.tobytes()


@pytest.fixture
def mock_pipeline_result():
    return BookResult(
        fields={
            "title": ProcessedField(value="Clean Architecture", confidence=0.95, boxes=[FieldBox(image="front", bbox=(0.1, 0.1, 0.8, 0.3))]),
            "subtitle": ProcessedField(),
            "authors": ProcessedField(value=["Robert C. Martin"], confidence=0.92, boxes=[FieldBox(image="front", bbox=(0.2, 0.3, 0.8, 0.4))]),
            "publisher": ProcessedField(value="Prentice Hall", confidence=0.88, boxes=[FieldBox(image="back", bbox=(0.2, 0.8, 0.6, 0.9))]),
            "isbn10": ProcessedField(),
            "isbn13": ProcessedField(value="9780134494166", confidence=0.98, boxes=[FieldBox(image="back", bbox=(0.5, 0.8, 0.9, 0.9))]),
            "year": ProcessedField(value=2017, confidence=0.85),
            "edition": ProcessedField(),
            "language": ProcessedField(value="English", confidence=0.9),
            "series": ProcessedField(),
        },
        overall_confidence=0.92,
        needs_review=False,
        warnings=[],
        ocr_lines=[],
        images=ImageDimensions(front=ImageMeta(width=100, height=200), back=ImageMeta(width=300, height=400)),
        image_hash="mockcombinedhash12345",
    )


def test_api_upload_front_only(mock_pipeline_result):
    _PIPELINE_CACHE.clear()
    img_bytes = _make_dummy_image(100, 200, 70)
    with patch("app.api.routes.books.process_book_images", return_value=mock_pipeline_result):
        files = {"front": ("cover.png", io.BytesIO(img_bytes), "image/png")}
        res = client.post("/books/upload", files=files)
        assert res.status_code == 200
        data = res.json()
        assert data["title"] == "Clean Architecture"
        assert data["front_image_url"].startswith("/books/")
        assert data["back_image_url"] is None

        # Verify serving front image
        img_res = client.get(f"/books/{data['id']}/image?side=front")
        assert img_res.status_code == 200
        assert img_res.content == img_bytes

        # Verify 404 for missing back image
        bad_side_res = client.get(f"/books/{data['id']}/image?side=back")
        assert bad_side_res.status_code == 404


def test_api_upload_front_and_back_returns_different_bytes(mock_pipeline_result):
    _PIPELINE_CACHE.clear()
    front_bytes = _make_dummy_image(100, 200, 80)
    back_bytes = _make_dummy_image(300, 400, 90)
    with patch("app.api.routes.books.process_book_images", return_value=mock_pipeline_result):
        files = {
            "front": ("front.png", io.BytesIO(front_bytes), "image/png"),
            "back": ("back.png", io.BytesIO(back_bytes), "image/png"),
        }
        res = client.post("/books/upload", files=files)
        assert res.status_code == 200
        data = res.json()
        assert data["front_image_url"] is not None
        assert data["back_image_url"] is not None

        # Both images should be servable and return different bytes
        res_front = client.get(f"/books/{data['id']}/image?side=front&v=1")
        res_back = client.get(f"/books/{data['id']}/image?side=back&v=1")
        assert res_front.status_code == 200
        assert res_back.status_code == 200
        assert res_front.content == front_bytes
        assert res_back.content == back_bytes
        assert res_front.content != res_back.content

        # Invalid side returns 400
        assert client.get(f"/books/{data['id']}/image?side=invalid").status_code == 400


def test_api_upload_missing_front():
    res = client.post("/books/upload", files={})
    assert res.status_code == 400
    assert "Front cover image is required" in res.json()["detail"]


def test_api_upload_bad_back_file():
    front_bytes = _make_dummy_image(100, 200, 100)
    files = {
        "front": ("front.png", io.BytesIO(front_bytes), "image/png"),
        "back": ("back.txt", io.BytesIO(b"not-an-image"), "text/plain"),
    }
    res = client.post("/books/upload", files=files)
    assert res.status_code == 400
    assert "Back cover validation error" in res.json()["detail"]

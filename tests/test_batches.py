"""Integration tests for bulk upload batches, queue execution, and error handling."""

import asyncio
import io
import json
from unittest.mock import MagicMock, patch
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.db.models import Batch, Book, Job
from app.db.session import SessionLocal, init_db
from app.main import app
from app.schemas.book import BookResult, FieldBox, ImageDimensions, ImageMeta, ProcessedField
from app.services.queue import _process_job, recover_pending_jobs

init_db()
client = TestClient(app)


def _dummy_image(w: int = 80, h: int = 120, val: int = 100) -> bytes:
    arr = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
    _, enc = cv2.imencode(".png", arr)
    return enc.tobytes()


@pytest.fixture
def mock_result():
    return BookResult(
        fields={
            "title": ProcessedField(value="Bulk Book Title", confidence=0.9),
            "subtitle": ProcessedField(),
            "authors": ProcessedField(value=["Bulk Author"], confidence=0.88),
            "publisher": ProcessedField(value="Bulk Pub", confidence=0.85),
            "isbn10": ProcessedField(),
            "isbn13": ProcessedField(value="9780134494166", confidence=0.95),
            "year": ProcessedField(value=2020, confidence=0.8),
            "edition": ProcessedField(),
            "language": ProcessedField(value="English", confidence=0.9),
            "series": ProcessedField(),
        },
        overall_confidence=0.88,
        needs_review=False,
        warnings=[],
        ocr_lines=[],
        images=ImageDimensions(front=ImageMeta(width=80, height=120)),
        image_hash="bulkhash12345",
    )


def test_create_batch_validation_and_size_limit():
    """Verify batch size limit of 50 books and file validation reporting."""
    # Exceed limit
    too_many = [{"label": f"Book {i}", "front_index": 0} for i in range(51)]
    img = _dummy_image(80, 80, 50)
    files = [("files", ("f0.png", io.BytesIO(img), "image/png"))]
    res = client.post("/batches", data={"items": json.dumps(too_many)}, files=files)
    assert res.status_code == 400
    assert "Maximum allowed batch size" in res.json()["detail"]

    # Valid batch with 1 valid pair and 1 corrupt file
    items = [
        {"label": "Book Valid", "front_index": 0, "back_index": None},
        {"label": "Book Corrupt", "front_index": 1, "back_index": None},
    ]
    files = [
        ("files", ("good.png", io.BytesIO(img), "image/png")),
        ("files", ("bad.png", io.BytesIO(b"not an image"), "image/png")),
    ]
    res = client.post("/batches", data={"items": json.dumps(items)}, files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["batch_id"] > 0
    assert data["total_jobs"] == 1
    assert len(data["skipped_items"]) == 1
    assert data["skipped_items"][0]["label"] == "Book Corrupt"


def test_batch_worker_execution_and_duplicate(mock_result):
    """Verify job processing to done, duplicate detection, and batch summary status."""
    img1 = _dummy_image(80, 80, int(np.random.randint(1, 250)))
    items = [{"label": "Batch Book A", "front_index": 0, "back_index": None}]
    files = [("files", ("f1.png", io.BytesIO(img1), "image/png"))]

    with patch("app.services.queue.process_book_images", return_value=mock_result):
        res = client.post("/batches", data={"items": json.dumps(items)}, files=files)
        assert res.status_code == 200
        batch_id = res.json()["batch_id"]
        job_id = res.json()["jobs"][0]["id"]

        # Run worker processing directly on the job
        asyncio.run(_process_job(job_id))

        summary_res = client.get(f"/batches/{batch_id}")
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert summary["counts"]["done"] == 1
        assert summary["done_count"] == 1
        assert summary["jobs"][0]["status"] == "done"
        assert summary["jobs"][0]["title"] == "Bulk Book Title"

        # Now upload the exact same image in another batch -> should become duplicate instantly
        res_dup = client.post("/batches", data={"items": json.dumps(items)}, files=[("files", ("f1.png", io.BytesIO(img1), "image/png"))])
        dup_batch_id = res_dup.json()["batch_id"]
        dup_job_id = res_dup.json()["jobs"][0]["id"]

        with patch("app.services.queue.process_book_images") as mock_pipeline:
            asyncio.run(_process_job(dup_job_id))
            assert not mock_pipeline.called  # no OCR/LLM on duplicate

        dup_summary = client.get(f"/batches/{dup_batch_id}").json()
        assert dup_summary["counts"]["duplicate"] == 1
        assert dup_summary["jobs"][0]["status"] == "duplicate"


def test_cancel_and_retry_endpoints():
    """Verify job cancellation and retry workflows."""
    img = _dummy_image(80, 80, 88)
    items = [{"label": "Cancel Me", "front_index": 0}]
    files = [("files", ("f.png", io.BytesIO(img), "image/png"))]
    res = client.post("/batches", data={"items": json.dumps(items)}, files=files)
    job_id = res.json()["jobs"][0]["id"]
    batch_id = res.json()["batch_id"]

    # Cancel queued job
    c_res = client.post(f"/jobs/{job_id}/cancel")
    assert c_res.status_code == 200
    assert c_res.json()["status"] == "canceled"

    # Retry canceled/failed job
    r_res = client.post(f"/jobs/{job_id}/retry")
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "queued"

    # Retry all failed in batch
    rf_res = client.post(f"/batches/{batch_id}/retry-failed")
    assert rf_res.status_code == 200


def test_startup_recovery():
    """Verify that jobs left in processing state reset to queued upon recovery."""
    db = SessionLocal()
    batch = Batch(total=1, label="Recovery Batch")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    job = Job(
        batch_id=batch.id,
        label="Interrupted Job",
        front_path="data/uploads/fake.jpg",
        status="processing",
        step="Reading text",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        recovered_count = asyncio.run(recover_pending_jobs())
        assert recovered_count >= 1

        db.refresh(job)
        assert job.status == "queued"
        assert job.step is None
    finally:
        db.delete(job)
        db.delete(batch)
        db.commit()
        db.close()


def test_job_retry_on_429(mock_result):
    """Verify that transient 429 errors are retried and eventually succeed."""
    img = _dummy_image(80, 80, 99)
    items = [{"label": "Retry 429 Book", "front_index": 0}]
    files = [("files", ("f429.png", io.BytesIO(img), "image/png"))]
    res = client.post("/batches", data={"items": json.dumps(items)}, files=files)
    job_id = res.json()["jobs"][0]["id"]
    batch_id = res.json()["batch_id"]

    call_count = 0

    def flaky_pipeline(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("429 Too Many Requests: Rate limit exceeded")
        return mock_result

    with patch("app.services.queue.process_book_images", side_effect=flaky_pipeline), \
         patch("asyncio.sleep", return_value=None):
        asyncio.run(_process_job(job_id))

    assert call_count == 2
    summary = client.get(f"/batches/{batch_id}").json()
    assert summary["jobs"][0]["status"] == "done"
    assert summary["jobs"][0]["attempts"] == 2

    # Test clear finished jobs
    del_res = client.delete(f"/batches/{batch_id}/finished")
    assert del_res.status_code == 200
    assert del_res.json()["cleared_count"] == 1
    after_summary = client.get(f"/batches/{batch_id}").json()
    assert len(after_summary["jobs"]) == 0

"""In-process background worker queue for processing bulk upload jobs."""

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Book, Job
from app.db.repository import create_book, get_by_hash
from app.db.session import SessionLocal
from app.services.pipeline import compute_combined_hash, process_book_images
from app.services.preprocess import ImageValidationError

logger = logging.getLogger(__name__)

_job_queue: Optional[asyncio.Queue] = None
_workers: list[asyncio.Task] = []


def get_queue() -> asyncio.Queue:
    global _job_queue
    if _job_queue is None:
        _job_queue = asyncio.Queue()
    return _job_queue


def enqueue_job(job_id: int) -> None:
    """Put a job ID on the in-process async processing queue."""
    q = get_queue()
    q.put_nowait(job_id)


def start_queue_workers(num_workers: Optional[int] = None) -> None:
    """Spawn background worker coroutines for the queue."""
    settings = get_settings()
    count = num_workers or settings.BULK_WORKERS
    q = get_queue()
    for i in range(count):
        task = asyncio.create_task(_worker_loop(q, i + 1))
        _workers.append(task)
    logger.info("Started %d bulk processing workers.", count)


def stop_queue_workers() -> None:
    """Cancel all active background worker tasks."""
    for task in _workers:
        task.cancel()
    _workers.clear()


async def recover_pending_jobs() -> int:
    """Reset processing jobs to queued on startup and re-enqueue all queued jobs."""
    db: Session = SessionLocal()
    try:
        # 1. Reset interrupted processing jobs
        stale_jobs = db.scalars(select(Job).where(Job.status == "processing")).all()
        for j in stale_jobs:
            j.status = "queued"
            j.step = None
            j.started_at = None
        db.commit()

        # 2. Enqueue all queued jobs
        queued_jobs = db.scalars(select(Job).where(Job.status == "queued")).all()
        for j in queued_jobs:
            enqueue_job(j.id)
        logger.info("Recovered %d stale jobs, enqueued %d total queued jobs.", len(stale_jobs), len(queued_jobs))
        return len(queued_jobs)
    finally:
        db.close()


def _update_job_step(job_id: int, step_text: str) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job and job.status == "processing":
            job.step = step_text
            db.commit()
    finally:
        db.close()


async def _worker_loop(queue: asyncio.Queue, worker_id: int) -> None:
    """Background worker continuously pulling and processing jobs from the queue."""
    logger.info("Worker #%d started.", worker_id)
    while True:
        try:
            job_id = await queue.get()
            await _process_job(job_id)
            queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Worker #%d unexpected error: %s", worker_id, exc)


async def _process_job(job_id: int) -> None:
    """Process a single job with duplicate check, retries for 429/transient errors, and state updates."""
    db: Session = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.status != "queued":
            return

        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.step = "Preprocessing"
        job.error = None
        db.commit()

        front_path = Path(job.front_path)
        back_path = Path(job.back_path) if job.back_path else None

        if not front_path.exists():
            job.status = "failed"
            job.error = f"Front image not found: {front_path.name}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        f_bytes = front_path.read_bytes()
        b_bytes = back_path.read_bytes() if back_path and back_path.exists() else None

        # Duplicate check before OCR/LLM
        combined_hash = compute_combined_hash(f_bytes, b_bytes)
        existing = get_by_hash(db, combined_hash)
        if existing:
            job.book_id = existing.id
            job.status = "duplicate"
            job.step = "Done"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("Job #%d is duplicate of book #%d", job_id, existing.id)
            return

        # Execute pipeline with retry policy (up to 3 attempts with exponential backoff)
        max_attempts = 3
        backoff_delays = [1.0, 2.0, 4.0]
        while job.attempts < max_attempts:
            job.attempts += 1
            db.commit()
            try:
                result = await asyncio.to_thread(
                    process_book_images,
                    f_bytes,
                    b_bytes,
                    lambda s: _update_job_step(job_id, s),
                )
                # Save book entity
                _update_job_step(job_id, "Saving")
                book_data = {
                    "title": result.fields["title"].value or job.label,
                    "subtitle": result.fields["subtitle"].value,
                    "authors": result.fields["authors"].value,
                    "publisher": result.fields["publisher"].value,
                    "isbn10": result.fields["isbn10"].value,
                    "isbn13": result.fields["isbn13"].value,
                    "year": result.fields["year"].value,
                    "edition": result.fields["edition"].value,
                    "language": result.fields["language"].value,
                    "series": result.fields["series"].value,
                    "confidence": result.overall_confidence,
                    "needs_review": result.needs_review,
                    "status": "pending",
                    "image_hash": combined_hash,
                    "front_image_path": str(front_path),
                    "back_image_path": str(back_path) if back_path else None,
                    "field_boxes": {k: v.model_dump() for k, v in result.fields.items()},
                    "ocr_lines": [line.model_dump() for line in result.ocr_lines],
                    "warnings": result.warnings,
                }
                book = create_book(db, book_data)
                job.book_id = book.id
                job.status = "done"
                job.step = "Done"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                logger.info("Job #%d succeeded -> book #%d", job_id, book.id)
                return
            except ImageValidationError as exc:
                job.status = "failed"
                job.error = f"Image validation error: {exc}"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                return
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "quota" in str(exc).lower() or "rate" in str(exc).lower()
                logger.warning("Job #%d attempt %d failed: %s", job_id, job.attempts, exc)
                if job.attempts < max_attempts and (is_rate_limit or "connection" in str(exc).lower() or "timeout" in str(exc).lower()):
                    delay = backoff_delays[min(job.attempts - 1, len(backoff_delays) - 1)]
                    await asyncio.sleep(delay)
                    continue
                else:
                    job.status = "failed"
                    job.error = str(exc)[:500]
                    job.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    return
    finally:
        db.close()

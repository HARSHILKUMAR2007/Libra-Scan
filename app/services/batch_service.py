"""Batch creation, file persistence, summary computation, and job management."""

import json
from pathlib import Path
import uuid
from typing import Optional
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Batch, Job
from app.services.preprocess import ImageValidationError, validate_and_decode
from app.services.queue import enqueue_job

MAX_BATCH_BOOKS = 50


async def create_batch_with_files(
    db: Session,
    items_raw: str,
    files: list[UploadFile],
    upload_dir: Path,
) -> dict:
    """Validate uploaded items and files, stream to disk immediately, create batch & jobs, and enqueue."""
    try:
        items = json.loads(items_raw)
        if not isinstance(items, list):
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid items JSON format. Expected list of book items.")

    if len(items) > MAX_BATCH_BOOKS:
        raise HTTPException(status_code=400, detail=f"Maximum allowed batch size is {MAX_BATCH_BOOKS} books.")

    upload_dir.mkdir(parents=True, exist_ok=True)

    # Read and validate each file once
    cached_file_bytes: dict[int, bytes] = {}
    file_errors: dict[int, str] = {}
    for idx, f in enumerate(files):
        content = await f.read()
        try:
            validate_and_decode(content)
            cached_file_bytes[idx] = content
        except ImageValidationError as exc:
            file_errors[idx] = str(exc)

    batch_uid = uuid.uuid4().hex[:8]
    created_jobs = []
    skipped_items = []

    batch = Batch(total=0, label=f"Batch {batch_uid}")
    db.add(batch)
    db.commit()
    db.refresh(batch)

    for item_idx, item in enumerate(items):
        f_idx = item.get("front_index")
        b_idx = item.get("back_index")
        label = item.get("label") or f"Book {item_idx + 1}"

        if f_idx is None or f_idx not in cached_file_bytes:
            err = file_errors.get(f_idx, "Front cover file missing or invalid")
            skipped_items.append({"label": label, "error": err})
            continue

        if b_idx is not None and b_idx not in cached_file_bytes:
            err = file_errors.get(b_idx, "Back cover file invalid")
            skipped_items.append({"label": label, "error": err})
            continue

        # Save files to disk immediately
        f_ext = Path(files[f_idx].filename or "front.jpg").suffix.lower() or ".jpg"
        f_path = upload_dir / f"bulk_{batch.id}_{item_idx}_front{f_ext}"
        f_path.write_bytes(cached_file_bytes[f_idx])

        b_path = None
        if b_idx is not None:
            b_ext = Path(files[b_idx].filename or "back.jpg").suffix.lower() or ".jpg"
            b_path = upload_dir / f"bulk_{batch.id}_{item_idx}_back{b_ext}"
            b_path.write_bytes(cached_file_bytes[b_idx])

        job = Job(
            batch_id=batch.id,
            label=label,
            front_path=str(f_path),
            back_path=str(b_path) if b_path else None,
            status="queued",
        )
        db.add(job)
        created_jobs.append(job)

    batch.total = len(created_jobs)
    db.commit()

    # Enqueue jobs
    for j in created_jobs:
        db.refresh(j)
        enqueue_job(j.id)

    return {
        "batch_id": batch.id,
        "total_jobs": len(created_jobs),
        "skipped_items": skipped_items,
        "jobs": [j.to_dict() for j in created_jobs],
    }


def get_batch_summary(db: Session, batch_id: int) -> dict:
    """Compute aggregate counts and list of jobs for a batch."""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    jobs = db.scalars(select(Job).where(Job.batch_id == batch_id).order_by(Job.id.asc())).all()

    counts = {"queued": 0, "processing": 0, "done": 0, "duplicate": 0, "failed": 0, "canceled": 0}
    durations = []

    for j in jobs:
        counts[j.status] = counts.get(j.status, 0) + 1
        if j.status in ("done", "duplicate", "failed") and j.started_at and j.finished_at:
            durations.append((j.finished_at - j.started_at).total_seconds())

    avg_secs = round(sum(durations) / len(durations), 1) if durations else 0.0

    return {
        "id": batch.id,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "total": batch.total,
        "label": batch.label,
        "counts": counts,
        "done_count": counts["done"] + counts["duplicate"],
        "avg_seconds_per_job": avg_secs,
        "jobs": [j.to_dict() for j in jobs],
    }


def get_active_batches(db: Session) -> dict:
    """Return active batch IDs containing queued or processing jobs."""
    active_stmt = (
        select(Job.batch_id)
        .where(Job.status.in_(["queued", "processing"]))
        .distinct()
    )
    active_batch_ids = list(db.scalars(active_stmt).all())
    active_count = db.query(Job).filter(Job.status.in_(["queued", "processing"])).count()
    return {"active_batch_ids": active_batch_ids, "active_job_count": active_count}


def retry_job_by_id(db: Session, job_id: int) -> dict:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "canceled"):
        raise HTTPException(status_code=400, detail=f"Cannot retry job in '{job.status}' status")
    job.status = "queued"
    job.step = None
    job.error = None
    job.attempts = 0
    job.started_at = None
    job.finished_at = None
    db.commit()
    enqueue_job(job.id)
    return job.to_dict()


def cancel_job_by_id(db: Session, job_id: int) -> dict:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "queued":
        raise HTTPException(status_code=400, detail="Only queued jobs can be canceled.")
    job.status = "canceled"
    job.step = "Canceled"
    db.commit()
    return job.to_dict()


def retry_failed_jobs_in_batch(db: Session, batch_id: int) -> dict:
    failed = db.scalars(select(Job).where(Job.batch_id == batch_id, Job.status == "failed")).all()
    for j in failed:
        j.status = "queued"
        j.step = None
        j.error = None
        j.attempts = 0
        enqueue_job(j.id)
    db.commit()
    return {"retried_count": len(failed)}


def clear_finished_jobs_in_batch(db: Session, batch_id: int) -> dict:
    finished = db.scalars(
        select(Job).where(Job.batch_id == batch_id, Job.status.in_(["done", "duplicate", "canceled"]))
    ).all()
    count = len(finished)
    for j in finished:
        db.delete(j)
    db.commit()
    return {"cleared_count": count}

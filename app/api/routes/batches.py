"""API endpoints for bulk upload batches, queue management, and thumbnail serving."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job
from app.db.session import get_db
from app.services.batch_service import (
    cancel_job_by_id,
    clear_finished_jobs_in_batch,
    create_batch_with_files,
    get_active_batches,
    get_batch_summary,
    retry_failed_jobs_in_batch,
    retry_job_by_id,
)

router = APIRouter(tags=["batches"])


@router.post("/batches")
async def create_batch(
    items: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Create a new bulk upload batch, save files immediately, and enqueue processing jobs."""
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR)
    return await create_batch_with_files(db, items, files, upload_dir)


@router.get("/batches/active")
def get_active_batches_endpoint(db: Session = Depends(get_db)):
    """Return active batch IDs for sidebar progress notification."""
    return get_active_batches(db)


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed status, counts, and job records for a batch."""
    return get_batch_summary(db, batch_id)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)):
    """Re-enqueue a failed or canceled job."""
    return retry_job_by_id(db, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    """Cancel a currently queued job."""
    return cancel_job_by_id(db, job_id)


@router.post("/batches/{batch_id}/retry-failed")
def retry_failed_jobs(batch_id: int, db: Session = Depends(get_db)):
    """Re-enqueue all failed jobs in a batch."""
    return retry_failed_jobs_in_batch(db, batch_id)


@router.delete("/batches/{batch_id}/finished")
def clear_finished_jobs(batch_id: int, db: Session = Depends(get_db)):
    """Remove done, duplicate, and canceled jobs from the batch view."""
    return clear_finished_jobs_in_batch(db, batch_id)


@router.get("/batches/jobs/{job_id}/image")
def get_job_image(
    job_id: int,
    side: str = Query("front"),
    db: Session = Depends(get_db),
):
    """Serve thumbnail for a job from disk even before book creation."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    clean_side = side.strip().lower()
    target_path = job.front_path if clean_side == "front" else job.back_path
    if not target_path or not Path(target_path).exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(target_path)

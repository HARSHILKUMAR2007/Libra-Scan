"""API endpoints for book processing, catalog queries, and image serving."""

import csv
import io
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.repository import create_book, delete_book, get_book, get_by_hash, list_books, update_book
from app.db.session import get_db
from app.services.pipeline import compute_combined_hash, process_book_images
from app.services.preprocess import ImageValidationError, validate_and_decode

router = APIRouter(prefix="/books", tags=["books"])


class BookUpdate(BaseModel):
    """Payload for librarian manual verification and corrections."""

    title: Optional[str] = None
    subtitle: Optional[str] = None
    authors: Optional[list[str]] = None
    publisher: Optional[str] = None
    isbn10: Optional[str] = None
    isbn13: Optional[str] = None
    year: Optional[int] = None
    edition: Optional[str] = None
    language: Optional[str] = None
    series: Optional[str] = None
    status: Optional[str] = "confirmed"


@router.post("/upload")
async def upload_book_images(
    front: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    back: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Upload front and optional back cover images with merged OCR extraction."""
    settings = get_settings()
    front_file = front or file
    if not front_file:
        raise HTTPException(status_code=400, detail="Front cover image is required.")

    f_bytes = await front_file.read()
    if not f_bytes:
        raise HTTPException(status_code=400, detail="Front cover file is empty.")
    try:
        validate_and_decode(f_bytes)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Front cover validation error: {exc}")

    b_bytes: Optional[bytes] = None
    if back and back.filename:
        b_bytes = await back.read()
        if b_bytes:
            try:
                validate_and_decode(b_bytes)
            except ImageValidationError as exc:
                raise HTTPException(status_code=400, detail=f"Back cover validation error: {exc}")

    combined_hash = compute_combined_hash(f_bytes, b_bytes)
    existing = get_by_hash(db, combined_hash)
    if existing:
        return existing.to_dict()

    try:
        result = process_book_images(f_bytes, b_bytes)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Processing error: {exc}")

    f_ext = Path(front_file.filename or "cover.jpg").suffix.lower() or ".jpg"
    front_path = Path(settings.UPLOAD_DIR) / f"{combined_hash}_front{f_ext}"
    front_path.write_bytes(f_bytes)

    back_path: Optional[Path] = None
    if b_bytes:
        b_ext = Path(back.filename or "back.jpg").suffix.lower() or ".jpg"
        back_path = Path(settings.UPLOAD_DIR) / f"{combined_hash}_back{b_ext}"
        back_path.write_bytes(b_bytes)

    book_data = {
        "title": result.fields["title"].value,
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
    return create_book(db, book_data).to_dict()


@router.get("")
def get_all_books(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return [b.to_dict() for b in list_books(db, status=status, skip=skip, limit=limit)]


@router.get("/export.csv")
def export_books_csv(db: Session = Depends(get_db)):
    books = list_books(db, limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "title", "authors", "publisher", "isbn10", "isbn13", "year", "confidence", "status"])
    for b in books:
        authors_str = ", ".join(b.authors) if b.authors else ""
        writer.writerow([b.id, b.title, authors_str, b.publisher, b.isbn10, b.isbn13, b.year, b.confidence, b.status])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=books.csv"})


@router.get("/{book_id}")
def get_single_book(book_id: int, db: Session = Depends(get_db)):
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book.to_dict()


@router.patch("/{book_id}")
def update_single_book(book_id: int, payload: BookUpdate, db: Session = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    updates.setdefault("status", "confirmed")
    book = update_book(db, book_id, updates)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book.to_dict()


@router.delete("/{book_id}")
def delete_single_book(book_id: int, db: Session = Depends(get_db)):
    if not delete_book(db, book_id):
        raise HTTPException(status_code=404, detail="Book not found")
    return {"status": "deleted"}


@router.get("/{book_id}/image")
def get_book_cover_image(
    book_id: int,
    side: str = Query("front"),
    v: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    book = get_book(db, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    clean_side = side.split("?")[0].strip().lower()
    if clean_side not in ("front", "back"):
        raise HTTPException(status_code=400, detail=f"Invalid side parameter '{side}'. Must be 'front' or 'back'.")
    target_path = book.front_image_path if clean_side == "front" else book.back_image_path
    if not target_path or not Path(target_path).exists():
        raise HTTPException(status_code=404, detail=f"Image for side '{clean_side}' not found")
    return FileResponse(target_path)

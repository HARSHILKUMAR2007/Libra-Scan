"""SQLAlchemy model definition for books, bulk batches, and queue jobs."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Book(Base):
    """Cataloged book entity storing extracted metadata, OCR lines, and review state."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(256), nullable=True)
    isbn10: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    isbn13: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    series: Mapped[str | None] = mapped_column(String(256), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    image_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    front_image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    back_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    field_boxes: Mapped[dict] = mapped_column(JSON, default=dict)
    ocr_lines: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Convert book model to dictionary including front and back image URLs."""
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "authors": self.authors,
            "publisher": self.publisher,
            "isbn10": self.isbn10,
            "isbn13": self.isbn13,
            "year": self.year,
            "edition": self.edition,
            "language": self.language,
            "series": self.series,
            "confidence": self.confidence,
            "needs_review": self.needs_review,
            "status": self.status,
            "image_hash": self.image_hash,
            "front_image_path": self.front_image_path,
            "back_image_path": self.back_image_path,
            "front_image_url": f"/books/{self.id}/image?side=front",
            "back_image_url": f"/books/{self.id}/image?side=back" if self.back_image_path else None,
            "field_boxes": self.field_boxes,
            "ocr_lines": self.ocr_lines,
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Batch(Base):
    """Bulk upload batch tracking overall progress and constituent jobs."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    total: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    jobs = relationship("Job", back_populates="batch", cascade="all, delete-orphan", order_by="Job.id")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total": self.total,
            "label": self.label,
        }


class Job(Base):
    """Individual book processing job within a bulk batch."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("batches.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    front_path: Mapped[str] = mapped_column(String(512), nullable=False)
    back_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="queued")
    step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    book_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    batch = relationship("Batch", back_populates="jobs")
    book = relationship("Book", foreign_keys=[book_id], lazy="joined")

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "batch_id": self.batch_id,
            "label": self.label,
            "front_path": self.front_path,
            "back_path": self.back_path,
            "front_url": f"/batches/jobs/{self.id}/image?side=front",
            "status": self.status,
            "step": self.step,
            "book_id": self.book_id,
            "error": self.error,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
        if self.book:
            data.update({
                "title": self.book.title,
                "authors": self.book.authors or [],
                "confidence": round(self.book.confidence or 0.0, 2),
                "needs_review": self.book.needs_review,
            })
        else:
            data.update({
                "title": None,
                "authors": [],
                "confidence": None,
                "needs_review": False,
            })
        return data

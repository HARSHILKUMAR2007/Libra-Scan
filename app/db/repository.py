"""Database repository operations for books."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Book


def create_book(session: Session, book_data: dict) -> Book:
    """Insert a new book record into the database."""
    book = Book(**book_data)
    session.add(book)
    session.commit()
    session.refresh(book)
    return book


def get_book(session: Session, book_id: int) -> Optional[Book]:
    """Retrieve a book by primary key ID."""
    return session.get(Book, book_id)


def get_by_hash(session: Session, image_hash: str) -> Optional[Book]:
    """Look up an existing book record by SHA-256 image hash."""
    stmt = select(Book).where(Book.image_hash == image_hash)
    return session.scalars(stmt).first()


def list_books(session: Session, status: Optional[str] = None, skip: int = 0, limit: int = 50) -> list[Book]:
    """Query books with optional status filtering and pagination ordered descending."""
    stmt = select(Book)
    if status:
        stmt = stmt.where(Book.status == status)
    stmt = stmt.order_by(Book.id.desc()).offset(skip).limit(limit)
    return list(session.scalars(stmt).all())


def update_book(session: Session, book_id: int, updates: dict) -> Optional[Book]:
    """Apply partial updates to a book record and synchronize field_boxes."""
    book = get_book(session, book_id)
    if not book:
        return None
    for key, value in updates.items():
        if hasattr(book, key):
            setattr(book, key, value)
    if book.field_boxes and isinstance(book.field_boxes, dict):
        fb = dict(book.field_boxes)
        for key, value in updates.items():
            if key in fb and isinstance(fb[key], dict):
                fb[key] = {**fb[key], "value": value}
        book.field_boxes = fb
    session.commit()
    session.refresh(book)
    return book


def delete_book(session: Session, book_id: int) -> bool:
    """Delete a book record by ID."""
    book = get_book(session, book_id)
    if not book:
        return False
    session.delete(book)
    session.commit()
    return True

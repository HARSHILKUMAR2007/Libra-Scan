"""API endpoint for catalog statistics and dashboard analytics."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session

from app.db.models import Book
from app.db.session import get_db

router = APIRouter(tags=["stats"])

FIELDS = ["title", "authors", "publisher", "isbn13", "year", "language"]


@router.get("/stats")
def get_catalog_stats(db: Session = Depends(get_db)):
    """Compute catalog analytics and KPIs using SQL aggregate queries."""
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # 1. Totals and field confidence averages in a single aggregate query
    totals_query = select(
        func.count(Book.id).label("books"),
        func.sum(case((Book.needs_review.is_(True), 1), else_=0)).label("needs_review"),
        func.sum(case((Book.status == "confirmed", 1), else_=0)).label("confirmed"),
        func.sum(case((Book.status == "pending", 1), else_=0)).label("pending"),
        func.sum(case((func.date(Book.created_at) == today_str, 1), else_=0)).label("scanned_today"),
        func.sum(case((or_(Book.isbn13.is_(None), Book.isbn13 == ""), 1), else_=0)).label("isbn_missing"),
        func.coalesce(func.avg(Book.confidence), 0.0).label("avg_confidence"),
        *[
            func.coalesce(func.avg(func.json_extract(Book.field_boxes, f"$.{f}.confidence")), 0.0).label(f"fc_{f}")
            for f in FIELDS
        ],
    )
    row = db.execute(totals_query).one()

    total_books = int(row.books or 0)
    totals = {
        "books": total_books,
        "needs_review": int(row.needs_review or 0),
        "confirmed": int(row.confirmed or 0),
        "pending": int(row.pending or 0),
        "scanned_today": int(row.scanned_today or 0),
        "isbn_missing": int(row.isbn_missing or 0),
    }

    avg_confidence = round(float(row.avg_confidence or 0.0), 3)
    field_confidence = {
        f: round(float(getattr(row, f"fc_{f}") or 0.0), 3)
        for f in FIELDS
    }

    # 2. Per day over the last 30 days (zero-filled)
    days = [(now_utc.date() - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    start_day = days[0]
    per_day_stmt = (
        select(func.date(Book.created_at).label("day"), func.count(Book.id).label("cnt"))
        .where(func.date(Book.created_at) >= start_day)
        .group_by(func.date(Book.created_at))
    )
    day_counts = {r.day: r.cnt for r in db.execute(per_day_stmt).all()}
    per_day = [{"date": d, "count": int(day_counts.get(d, 0))} for d in days]

    # 3. Recent 6 books
    recent_stmt = select(Book).order_by(Book.created_at.desc(), Book.id.desc()).limit(6)
    recent_books = db.scalars(recent_stmt).all()
    recent = [
        {
            "id": b.id,
            "title": b.title or "Untitled",
            "authors": b.authors or [],
            "status": b.status or "pending",
            "confidence": round(float(b.confidence or 0.0), 2),
            "needs_review": bool(b.needs_review),
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "front_image_url": f"/books/{b.id}/image?side=front",
        }
        for b in recent_books
    ]

    # 4. Top publishers
    pub_stmt = (
        select(Book.publisher, func.count(Book.id).label("cnt"))
        .where(Book.publisher.isnot(None), Book.publisher != "")
        .group_by(Book.publisher)
        .order_by(func.count(Book.id).desc())
        .limit(5)
    )
    top_publishers = [{"name": r[0], "count": int(r[1])} for r in db.execute(pub_stmt).all()]

    # 5. Languages
    lang_stmt = (
        select(Book.language, func.count(Book.id).label("cnt"))
        .where(Book.language.isnot(None), Book.language != "")
        .group_by(Book.language)
        .order_by(func.count(Book.id).desc())
        .limit(5)
    )
    languages = [{"name": r[0], "count": int(r[1])} for r in db.execute(lang_stmt).all()]

    # 6. Publication years
    years_stmt = (
        select(Book.year, func.count(Book.id).label("cnt"))
        .where(Book.year.isnot(None))
        .group_by(Book.year)
        .order_by(Book.year.asc())
    )
    years = [{"year": int(r[0]), "count": int(r[1])} for r in db.execute(years_stmt).all()]

    # 7. Top authors (SQLite json_each aggregate)
    top_authors = []
    try:
        auth_stmt = text(
            """
            SELECT json_each.value AS author, COUNT(*) AS cnt
            FROM books, json_each(books.authors)
            WHERE books.authors IS NOT NULL 
              AND json_valid(books.authors) = 1 
              AND json_each.value IS NOT NULL 
              AND trim(json_each.value) != ''
            GROUP BY author
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
        top_authors = [{"name": str(r[0]), "count": int(r[1])} for r in db.execute(auth_stmt).all()]
    except Exception:
        top_authors = []

    return {
        "totals": totals,
        "avg_confidence": avg_confidence,
        "field_confidence": field_confidence,
        "per_day": per_day,
        "recent": recent,
        "top_authors": top_authors,
        "top_publishers": top_publishers,
        "languages": languages,
        "years": years,
    }

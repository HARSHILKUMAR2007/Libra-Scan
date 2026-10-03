"""Integration tests for catalog analytics and stats endpoint."""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Book
from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_stats_empty_db():
    """Verify stats endpoint returns valid empty structure with zeros when DB is empty."""
    res = client.get("/stats")
    assert res.status_code == 200
    data = res.json()

    assert "totals" in data
    assert "avg_confidence" in data
    assert "field_confidence" in data
    assert "per_day" in data
    assert "recent" in data
    assert "top_authors" in data
    assert "top_publishers" in data
    assert "languages" in data
    assert "years" in data

    assert data["totals"]["books"] >= 0
    assert len(data["per_day"]) == 30
    assert isinstance(data["field_confidence"], dict)


def test_stats_with_seeded_books():
    """Verify stats endpoint with seeded books calculates aggregates correctly."""
    # Seed specific books
    app_dependency = app.dependency_overrides.get(get_db)
    # Using existing DB session
    from app.db.session import SessionLocal

    db: Session = SessionLocal()
    try:
        b1 = Book(
            title="Design Patterns",
            authors=["Erich Gamma", "Richard Helm"],
            publisher="Addison-Wesley",
            isbn13="9780201633610",
            year=1994,
            language="English",
            confidence=0.95,
            needs_review=False,
            status="confirmed",
            image_hash="seedhash111",
            front_image_path="data/uploads/fake1.jpg",
            field_boxes={
                "title": {"value": "Design Patterns", "confidence": 0.98},
                "authors": {"value": ["Erich Gamma"], "confidence": 0.94},
                "publisher": {"value": "Addison-Wesley", "confidence": 0.90},
                "isbn13": {"value": "9780201633610", "confidence": 0.99},
                "year": {"value": 1994, "confidence": 0.92},
                "language": {"value": "English", "confidence": 0.96},
            },
            created_at=datetime.now(timezone.utc),
        )
        b2 = Book(
            title="Refactoring",
            authors=["Martin Fowler"],
            publisher="Addison-Wesley",
            isbn13="",  # missing isbn13
            year=1999,
            language="English",
            confidence=0.65,
            needs_review=True,
            status="pending",
            image_hash="seedhash222",
            front_image_path="data/uploads/fake2.jpg",
            field_boxes={
                "title": {"value": "Refactoring", "confidence": 0.70},
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(b1)
        db.add(b2)
        db.commit()

        res = client.get("/stats")
        assert res.status_code == 200
        stats = res.json()

        assert stats["totals"]["books"] >= 2
        assert stats["totals"]["needs_review"] >= 1
        assert stats["totals"]["confirmed"] >= 1
        assert stats["totals"]["pending"] >= 1
        assert stats["totals"]["scanned_today"] >= 2
        assert stats["totals"]["isbn_missing"] >= 1
        assert stats["avg_confidence"] > 0.0

        # Check publisher aggregate
        pubs = [p["name"] for p in stats["top_publishers"]]
        assert "Addison-Wesley" in pubs

        # Check per_day has 30 items
        assert len(stats["per_day"]) == 30
        assert any(d["count"] > 0 for d in stats["per_day"])

        # Check recent contains books
        assert len(stats["recent"]) > 0
        recent_titles = [r["title"] for r in stats["recent"]]
        assert "Refactoring" in recent_titles or "Design Patterns" in recent_titles

        # Clean up seeded books
        db.delete(b1)
        db.delete(b2)
        db.commit()
    finally:
        db.close()

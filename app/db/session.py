"""Database engine, session management, and startup schema initialization."""

from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""


def _get_engine():
    settings = get_settings()
    is_sqlite = settings.DATABASE_URL.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    return create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables on application initialization."""
    from pathlib import Path
    import app.db.models  # noqa: F401 - ensure models are imported
    settings = get_settings()
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""FastAPI main application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.batches import router as batches_router
from app.api.routes.books import router as books_router
from app.api.routes.health import router as health_router
from app.api.routes.stats import router as stats_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.services.queue import recover_pending_jobs, start_queue_workers, stop_queue_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown lifecycle events."""
    setup_logging()
    settings = get_settings()
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path("frontend").mkdir(parents=True, exist_ok=True)
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    init_db()
    start_queue_workers()
    await recover_pending_jobs()
    yield
    stop_queue_workers()


app = FastAPI(title="Book OCR", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(books_router)
app.include_router(stats_router)
app.include_router(batches_router)

# Mount frontend static directory after API routes
frontend_dir = Path("frontend")
frontend_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

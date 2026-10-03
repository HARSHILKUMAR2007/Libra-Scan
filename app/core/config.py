"""Application configuration management using pydantic-settings."""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    MAX_UPLOAD_MB: int = 10
    UPLOAD_DIR: str = "data/uploads"
    DATABASE_URL: str = "sqlite:///data/books.db"
    AZURE_DI_ENDPOINT: str = ""
    AZURE_DI_KEY: str = ""
    LLM_PROVIDER: Literal["gemini", "openai"] = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    MAX_IMAGE_SIDE: int = 2000
    OCR_MIN_CONFIDENCE: float = 0.5
    BULK_WORKERS: int = 2


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()

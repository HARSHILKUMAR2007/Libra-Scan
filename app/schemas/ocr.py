"""Pydantic schemas for OCR tokens, lines, and extraction results."""

from typing import Literal
from pydantic import BaseModel, Field


class OcrLine(BaseModel):
    """Normalized OCR detected text line."""

    id: int
    text: str
    polygon: list[tuple[float, float]] = Field(description="4 normalized points [(x, y), ...]")
    bbox: tuple[float, float, float, float] = Field(description="(x_min, y_min, x_max, y_max) normalized 0 to 1")
    confidence: float
    image: Literal["front", "back"] = "front"


class OcrResult(BaseModel):
    """Aggregated OCR result for a processed image."""

    lines: list[OcrLine]
    width: int
    height: int

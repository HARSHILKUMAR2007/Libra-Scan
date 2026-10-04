"""Pydantic schemas for book details and extraction results."""

from typing import Any, Generic, Literal, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ocr import OcrLine

T = TypeVar("T")


class FieldValue(BaseModel, Generic[T]):
    """Extracted field value accompanied by confidence score and source OCR line IDs."""

    value: Optional[T] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_line_ids: list[int] = Field(default_factory=list)


class BookDetails(BaseModel):
    """Structured cataloging details extracted from OCR text by the LLM."""

    model_config = ConfigDict(extra="forbid")

    is_book_cover: bool = True
    title: FieldValue[str] = Field(default_factory=FieldValue)
    subtitle: FieldValue[str] = Field(default_factory=FieldValue)
    authors: FieldValue[list[str]] = Field(default_factory=FieldValue)
    publisher: FieldValue[str] = Field(default_factory=FieldValue)
    isbn10: FieldValue[str] = Field(default_factory=FieldValue)
    isbn13: FieldValue[str] = Field(default_factory=FieldValue)
    edition: FieldValue[str] = Field(default_factory=FieldValue)
    year: FieldValue[int] = Field(default_factory=FieldValue)
    language: FieldValue[str] = Field(default_factory=FieldValue)
    series: FieldValue[str] = Field(default_factory=FieldValue)


class FieldBox(BaseModel):
    """Bounding box bound to either front or back cover image."""

    image: Literal["front", "back"]
    bbox: tuple[float, float, float, float]


class ProcessedField(BaseModel):
    """Enriched field details containing normalized merged bounding boxes per image."""

    value: Any = None
    confidence: float = 0.0
    boxes: list[FieldBox] = Field(default_factory=list)


class ImageMeta(BaseModel):
    width: int
    height: int


class ImageDimensions(BaseModel):
    front: ImageMeta
    back: Optional[ImageMeta] = None


class BookResult(BaseModel):
    """Consolidated result of the book covers OCR and extraction pipeline."""

    fields: dict[str, ProcessedField]
    overall_confidence: float
    needs_review: bool
    warnings: list[str] = Field(default_factory=list)
    ocr_lines: list[OcrLine]
    images: ImageDimensions
    image_hash: str

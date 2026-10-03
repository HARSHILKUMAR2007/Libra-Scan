"""Unit tests for LLM metadata extraction with mocked providers."""

import json
from unittest.mock import MagicMock, patch
import pytest
from app.schemas.ocr import OcrLine, OcrResult
from app.services.llm import extract_book, format_position


def test_format_position():
    line = OcrLine(id=0, text="Title", polygon=[(0, 0), (1, 0), (1, 0.1), (0, 0.1)], bbox=(0.1, 0.1, 0.9, 0.2), confidence=0.9)
    pos = format_position(line)
    assert "top" in pos
    assert "center" in pos
    assert "large" in pos


def test_extract_book_mocked(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.5-flash")

    from app.core.config import get_settings

    get_settings.cache_clear()

    fake_response = {
        "title": {"value": "The Great Gatsby", "confidence": 0.95, "source_line_ids": [0]},
        "subtitle": {"value": None, "confidence": 0.0, "source_line_ids": []},
        "authors": {"value": ["F. Scott Fitzgerald"], "confidence": 0.92, "source_line_ids": [1]},
        "publisher": {"value": "Scribner", "confidence": 0.85, "source_line_ids": [2]},
        "isbn10": {"value": None, "confidence": 0.0, "source_line_ids": []},
        "isbn13": {"value": "9780743273565", "confidence": 0.9, "source_line_ids": [3]},
        "edition": {"value": None, "confidence": 0.0, "source_line_ids": []},
        "year": {"value": 1925, "confidence": 0.8, "source_line_ids": [4]},
        "language": {"value": "English", "confidence": 0.9, "source_line_ids": []},
        "series": {"value": None, "confidence": 0.0, "source_line_ids": []},
    }

    ocr = OcrResult(
        lines=[
            OcrLine(id=0, text="The Great Gatsby", polygon=[(0, 0), (1, 0), (1, 0.1), (0, 0.1)], bbox=(0.1, 0.1, 0.9, 0.2), confidence=0.95),
            OcrLine(id=1, text="F. Scott Fitzgerald", polygon=[(0, 0.3), (1, 0.3), (1, 0.4), (0, 0.4)], bbox=(0.2, 0.3, 0.8, 0.4), confidence=0.92),
        ],
        width=800,
        height=1200,
    )

    with patch("app.services.llm._call_gemini", return_value=json.dumps(fake_response)):
        details = extract_book(ocr)
        assert details.title.value == "The Great Gatsby"
        assert details.authors.value == ["F. Scott Fitzgerald"]
        assert details.year.value == 1925
        assert details.title.source_line_ids == [0]


def test_extract_book_retry_failure(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")
    from app.core.config import get_settings

    get_settings.cache_clear()

    ocr = OcrResult(lines=[], width=100, height=100)
    with patch("app.services.llm._call_gemini", return_value="invalid-json"):
        with pytest.raises(ValueError, match="LLM extraction failed after retry"):
            extract_book(ocr)

"""Unit tests for OCR service with mocked Azure Document Intelligence."""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from app.services.ocr import _normalize_polygon, run_ocr


def test_normalize_polygon():
    raw_polygon = [100, 200, 300, 200, 300, 400, 100, 400]
    points = _normalize_polygon(raw_polygon, 1000, 1000)
    assert len(points) == 4
    assert points[0] == (0.1, 0.2)
    assert points[2] == (0.3, 0.4)


def test_run_ocr_mocked(monkeypatch):
    monkeypatch.setenv("AZURE_DI_ENDPOINT", "https://mock-ocr.cognitiveservices.azure.com/")
    monkeypatch.setenv("AZURE_DI_KEY", "mock-key")

    from app.core.config import get_settings

    get_settings.cache_clear()

    # Create fake page and lines
    line1 = MagicMock()
    line1.content = "BOOK TITLE"
    line1.polygon = [50, 50, 450, 50, 450, 100, 50, 100]
    w1 = MagicMock(confidence=0.95)
    line1.words = [w1]

    line2 = MagicMock()
    line2.content = "Author Name"
    line2.polygon = [50, 200, 300, 200, 300, 250, 50, 250]
    w2 = MagicMock(confidence=0.88)
    line2.words = [w2]

    # Line with confidence below threshold
    line_low = MagicMock()
    line_low.content = "Noise"
    line_low.polygon = [10, 10, 50, 10, 50, 30, 10, 30]
    line_low.words = [MagicMock(confidence=0.2)]

    mock_result = MagicMock()
    mock_page = MagicMock()
    mock_page.lines = [line2, line_low, line1]  # Unsorted order
    mock_result.pages = [mock_page]

    with patch("app.services.ocr.DocumentIntelligenceClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result
        mock_client.begin_analyze_document.return_value = mock_poller

        img = np.zeros((500, 500, 3), dtype=np.uint8)
        res = run_ocr(img)

        # Ensure low confidence line was dropped
        assert len(res.lines) == 2
        # Ensure lines are sorted top to bottom
        assert res.lines[0].text == "BOOK TITLE"
        assert res.lines[0].id == 0
        assert res.lines[1].text == "Author Name"
        assert res.lines[1].id == 1
        # Check normalized coordinates
        assert res.lines[0].bbox[1] == pytest.approx(0.1)

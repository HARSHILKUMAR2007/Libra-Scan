"""OCR extraction service using Azure Document Intelligence with GA fallback."""

import io
import logging
import time
from typing import Any
import cv2
import httpx
import numpy as np
try:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import ResourceNotFoundError
except ImportError:
    class DocumentIntelligenceClient:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("Azure Document Intelligence SDK is not installed. Please install azure-ai-documentintelligence.")

    class AzureKeyCredential:  # type: ignore
        def __init__(self, key: str):
            self.key = key

    ResourceNotFoundError = Exception  # type: ignore

from app.core.config import get_settings
from app.schemas.ocr import OcrLine, OcrResult

logger = logging.getLogger(__name__)


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to read property from dict or model instance."""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _normalize_polygon(raw_polygon: list, width: int, height: int) -> list[tuple[float, float]]:
    """Convert raw polygon coordinates to normalized (0 to 1) 4-point list."""
    points: list[tuple[float, float]] = []
    if raw_polygon and isinstance(raw_polygon[0], (int, float)):
        for i in range(0, len(raw_polygon), 2):
            px = max(0.0, min(1.0, float(raw_polygon[i]) / width))
            py = max(0.0, min(1.0, float(raw_polygon[i + 1]) / height))
            points.append((px, py))
    else:
        for pt in raw_polygon or []:
            x = _get_val(pt, "x", pt[0] if isinstance(pt, (list, tuple)) else 0.0)
            y = _get_val(pt, "y", pt[1] if isinstance(pt, (list, tuple)) else 0.0)
            points.append((max(0.0, min(1.0, float(x) / width)), max(0.0, min(1.0, float(y) / height))))
    while len(points) < 4:
        points.append((0.0, 0.0))
    return points[:4]


def _call_formrecognizer_rest(endpoint: str, key: str, jpeg_bytes: bytes) -> dict:
    """Fallback REST polling client for Form Recognizer 2023-07-31 GA API."""
    url = f"{endpoint.rstrip('/')}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream"}
    with httpx.Client(timeout=30.0) as client:
        res = client.post(url, headers=headers, content=jpeg_bytes)
        res.raise_for_status()
        op_url = res.headers.get("Operation-Location")
        if not op_url:
            raise ValueError("Missing Operation-Location in Azure response")

        for _ in range(30):
            time.sleep(1.0)
            poll_res = client.get(op_url, headers={"Ocp-Apim-Subscription-Key": key})
            data = poll_res.json()
            if data.get("status") == "succeeded":
                return data.get("analyzeResult", {})
            if data.get("status") in ("failed", "canceled"):
                raise ValueError(f"Azure OCR analysis {data.get('status')}")
    raise TimeoutError("Azure OCR analysis timed out")


_logged_fallback = False


def _call_azure_read(client: DocumentIntelligenceClient, endpoint: str, key: str, jpeg_bytes: bytes):
    """Execute prebuilt-read with fallback to 2023-07-31 GA API on 404."""
    global _logged_fallback
    for attempt in range(2):
        try:
            poller = client.begin_analyze_document(
                "prebuilt-read",
                analyze_request=io.BytesIO(jpeg_bytes),
                content_type="application/octet-stream",
            )
            return poller.result()
        except (ResourceNotFoundError, Exception) as exc:
            if "404" in str(exc) or "Resource not found" in str(exc):
                if not _logged_fallback:
                    logger.info("Azure DocumentIntelligence preview endpoint returned 404; falling back to 2023-07-31 GA API")
                    _logged_fallback = True
                return _call_formrecognizer_rest(endpoint, key, jpeg_bytes)
            if attempt == 1:
                raise
            logger.warning("Azure OCR attempt %d failed (%s). Retrying...", attempt + 1, exc)
            time.sleep(1.0)


def run_ocr(image: np.ndarray) -> OcrResult:
    """Run Azure Document Intelligence OCR on a preprocessed BGR image."""
    settings = get_settings()
    if not settings.AZURE_DI_ENDPOINT or not settings.AZURE_DI_KEY:
        raise ValueError("AZURE_DI_ENDPOINT and AZURE_DI_KEY must be configured in .env")

    h, w = image.shape[:2]
    success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise ValueError("Failed to encode image to JPEG for OCR")

    endpoint = settings.AZURE_DI_ENDPOINT.rstrip("/")
    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(settings.AZURE_DI_KEY),
        api_version="2024-11-30",
    )

    start_time = time.perf_counter()
    result = _call_azure_read(client, endpoint, settings.AZURE_DI_KEY, encoded.tobytes())
    logger.info("Azure OCR finished in %.2fms", (time.perf_counter() - start_time) * 1000)

    raw_lines = []
    for page in _get_val(result, "pages", []) or []:
        for line in _get_val(page, "lines", []) or []:
            words = _get_val(line, "words", []) or []
            if words:
                confs = [_get_val(w, "confidence") for w in words if _get_val(w, "confidence") is not None]
                confidence = float(sum(confs) / len(confs)) if confs else 1.0
            else:
                confidence = float(_get_val(line, "confidence", 1.0) or 1.0)

            if confidence < settings.OCR_MIN_CONFIDENCE:
                continue

            polygon = _normalize_polygon(_get_val(line, "polygon", []), w, h)
            xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
            raw_lines.append({
                "text": str(_get_val(line, "content", "")),
                "polygon": polygon,
                "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "confidence": confidence,
            })

    raw_lines.sort(key=lambda item: item["bbox"][1])
    sorted_lines = [
        OcrLine(id=idx, text=l["text"], polygon=l["polygon"], bbox=l["bbox"], confidence=round(l["confidence"], 3))
        for idx, l in enumerate(raw_lines)
    ]
    return OcrResult(lines=sorted_lines, width=w, height=h)

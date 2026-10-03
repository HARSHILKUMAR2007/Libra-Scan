"""Unit tests for the image preprocessing pipeline."""

import cv2
import numpy as np
import pytest
from app.core.config import get_settings
from app.services.preprocess import ImageValidationError, preprocess


def make_image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    """Generate in-memory image bytes with the specified dimensions and format."""
    arr = np.full((height, width, 3), 128, dtype=np.uint8)
    # Add simple texture/shape for realistic CLAHE and filter execution
    cv2.circle(arr, (width // 2, height // 2), min(width, height) // 4, (255, 0, 0), -1)
    success, encoded = cv2.imencode(f".{fmt.lower()}", arr)
    assert success
    return encoded.tobytes()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_valid_image_decoding(fmt: str) -> None:
    """Valid PNG and JPEG bytes decode and return matching dimensions."""
    data = make_image_bytes(200, 300, fmt)
    proc, meta = preprocess(data)
    assert meta["original_width"] == 200
    assert meta["original_height"] == 300
    assert proc.shape == (300, 200, 3)


def test_downscale_oversize_image() -> None:
    """Image larger than MAX_IMAGE_SIDE is downscaled preserving aspect ratio."""
    settings = get_settings()
    orig_w, orig_h = settings.MAX_IMAGE_SIDE * 2, settings.MAX_IMAGE_SIDE
    data = make_image_bytes(orig_w, orig_h, "PNG")

    proc, meta = preprocess(data)
    assert max(meta["processed_width"], meta["processed_height"]) == settings.MAX_IMAGE_SIDE
    assert meta["scale"] == pytest.approx(settings.MAX_IMAGE_SIDE / orig_w, rel=1e-2)
    assert proc.shape[0] == meta["processed_height"]
    assert proc.shape[1] == meta["processed_width"]


def test_small_image_not_upscaled() -> None:
    """Images smaller than MAX_IMAGE_SIDE retain original dimensions and scale 1.0."""
    data = make_image_bytes(150, 150, "PNG")
    proc, meta = preprocess(data)
    assert meta["scale"] == 1.0
    assert meta["processed_width"] == 150
    assert meta["processed_height"] == 150
    assert proc.shape == (150, 150, 3)


def test_unsupported_or_corrupt_file_raises() -> None:
    """Corrupt or non-image payloads raise ImageValidationError."""
    with pytest.raises(ImageValidationError):
        preprocess(b"not-a-valid-image-stream")

    # Valid BMP format but not allowed in (JPEG, PNG, WEBP)
    arr = np.zeros((50, 50, 3), dtype=np.uint8)
    _, bmp_bytes = cv2.imencode(".bmp", arr)
    with pytest.raises(ImageValidationError):
        preprocess(bmp_bytes.tobytes())


def test_oversize_file_raises() -> None:
    """Payloads exceeding MAX_UPLOAD_MB raise ImageValidationError."""
    settings = get_settings()
    oversize_bytes = b"0" * (settings.MAX_UPLOAD_MB * 1024 * 1024 + 1024)
    with pytest.raises(ImageValidationError, match="exceeds"):
        preprocess(oversize_bytes)


def test_output_array_format() -> None:
    """Processed image must be a 3-channel uint8 array."""
    data = make_image_bytes(100, 100, "PNG")
    proc, _ = preprocess(data)
    assert isinstance(proc, np.ndarray)
    assert proc.dtype == np.uint8
    assert proc.ndim == 3
    assert proc.shape[2] == 3

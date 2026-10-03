"""Image preprocessing pipeline for book cover OCR."""

import io
import logging
import time
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ENABLED_STEPS = {
    "fix_orientation": True,
    "resize_max_side": True,
    "enhance_contrast": True,
    "denoise": True,
    "sharpen": True,
}


class ImageValidationError(Exception):
    """Raised when an image fails format, size, or decoding validation."""


def validate_and_decode(image_bytes: bytes) -> Image.Image:
    """Validate image format and size, returning a verified PIL Image."""
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(image_bytes) > max_bytes:
        raise ImageValidationError(f"File size exceeds {settings.MAX_UPLOAD_MB}MB limit")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ImageValidationError(f"Unsupported format '{img.format}'. Allowed: JPEG, PNG, WEBP")
        img.load()
        return img
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError(f"Cannot decode image: {exc}") from exc


def fix_orientation(img: Image.Image) -> np.ndarray:
    """Apply EXIF orientation and convert to OpenCV BGR array."""
    transposed = ImageOps.exif_transpose(img)
    rgb = transposed if transposed.mode == "RGB" else transposed.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def resize_max_side(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Downscale image keeping aspect ratio if longest side exceeds max_side."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img, 1.0
    scale = max_side / longest
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA), float(new_w / w)


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """Enhance contrast using CLAHE on the LAB lightness channel."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def denoise(img: np.ndarray) -> np.ndarray:
    """Apply mild bilateral filtering to preserve edges while reducing noise."""
    return cv2.bilateralFilter(img, d=7, sigmaColor=50, sigmaSpace=50)


def sharpen(img: np.ndarray) -> np.ndarray:
    """Apply mild unsharp masking."""
    blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=1.0)
    return cv2.addWeighted(img, 1.6, blurred, -0.6, 0)


def preprocess(image_bytes: bytes) -> tuple[np.ndarray, dict]:
    """Execute preprocessing pipeline on image bytes and return BGR image with metadata."""
    start = time.perf_counter()
    logger.debug("Starting image preprocessing")
    settings = get_settings()

    pil_img = validate_and_decode(image_bytes)
    steps_applied = ["validate_and_decode"]

    if ENABLED_STEPS.get("fix_orientation", True):
        logger.debug("Applying step: fix_orientation")
        img = fix_orientation(pil_img)
        steps_applied.append("fix_orientation")
    else:
        img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)

    orig_h, orig_w = img.shape[:2]
    scale = 1.0
    if ENABLED_STEPS.get("resize_max_side", True):
        logger.debug("Applying step: resize_max_side")
        img, scale = resize_max_side(img, settings.MAX_IMAGE_SIDE)
        steps_applied.append("resize_max_side")

    for name, func in [("enhance_contrast", enhance_contrast), ("denoise", denoise), ("sharpen", sharpen)]:
        if ENABLED_STEPS.get(name, True):
            logger.debug("Applying step: %s", name)
            img = func(img)
            steps_applied.append(name)

    proc_h, proc_w = img.shape[:2]
    logger.info("Preprocessed in %.2fms (steps: %s)", (time.perf_counter() - start) * 1000, steps_applied)

    return img, {
        "original_width": orig_w,
        "original_height": orig_h,
        "processed_width": proc_w,
        "processed_height": proc_h,
        "scale": scale,
        "steps_applied": steps_applied,
    }

"""Debug script to run pipeline and save annotated images with field boxes and OCR line IDs."""

import sys
from pathlib import Path
import cv2
import numpy as np

# Ensure root dir is in python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.pipeline import process_book_images

COLOR_PALETTE = {
    "title": (235, 99, 37),       # BGR: blue
    "subtitle": (237, 58, 124),   # purple
    "authors": (105, 150, 5),     # green
    "publisher": (6, 119, 217),   # amber
    "isbn10": (119, 39, 219),     # magenta
    "isbn13": (178, 145, 8),      # cyan
    "year": (13, 163, 101),       # lime
    "edition": (229, 70, 79),     # indigo
    "language": (234, 51, 147),   # violet
    "series": (12, 88, 234),      # orange
}


def _draw_annotations(img_bgr: np.ndarray, side: str, result) -> np.ndarray:
    annotated = img_bgr.copy()
    h, w = annotated.shape[:2]

    # 1. Draw all OCR lines in lighter color with global ID
    side_lines = [l for l in result.ocr_lines if l.image == side]
    for line in side_lines:
        x1, y1, x2, y2 = [int(coord * dim) for coord, dim in zip(line.bbox, (w, h, w, h))]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (200, 200, 230), 1)
        cv2.putText(annotated, str(line.id), (x1 + 2, y1 + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 220), 1)

    # 2. Draw field boxes with colored labels
    for f_name, f_data in result.fields.items():
        color = COLOR_PALETTE.get(f_name, (255, 0, 0))
        for box in f_data.boxes:
            if box.image != side:
                continue
            bx1, by1, bx2, by2 = [int(c * d) for c, d in zip(box.bbox, (w, h, w, h))]
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, 2)

            label = f"{f_name.upper()}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            tag_y1 = max(0, by1 - th - 6)
            cv2.rectangle(annotated, (bx1, tag_y1), (bx1 + tw + 6, tag_y1 + th + 6), color, -1)
            cv2.putText(annotated, label, (bx1 + 3, tag_y1 + th + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    return annotated


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_boxes.py <front_image_path> [back_image_path]")
        sys.exit(1)

    front_path = Path(sys.argv[1])
    back_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not front_path.exists():
        print(f"Error: Front image not found at {front_path}")
        sys.exit(1)
    if back_path and not back_path.exists():
        print(f"Error: Back image not found at {back_path}")
        sys.exit(1)

    f_bytes = front_path.read_bytes()
    b_bytes = back_path.read_bytes() if back_path else None

    print(f"Running pipeline for front: {front_path.name}" + (f", back: {back_path.name}" if back_path else ""))
    result = process_book_images(f_bytes, b_bytes)

    out_dir = ROOT / "data" / "samples" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    f_img = cv2.imdecode(np.frombuffer(f_bytes, np.uint8), cv2.IMREAD_COLOR)
    f_annotated = _draw_annotations(f_img, "front", result)
    f_out = out_dir / "front_annotated.jpg"
    cv2.imwrite(str(f_out), f_annotated)
    print(f"Saved: {f_out}")

    if b_bytes:
        b_img = cv2.imdecode(np.frombuffer(b_bytes, np.uint8), cv2.IMREAD_COLOR)
        b_annotated = _draw_annotations(b_img, "back", result)
        b_out = out_dir / "back_annotated.jpg"
        cv2.imwrite(str(b_out), b_annotated)
        print(f"Saved: {b_out}")

    print("\nExtraction Summary:")
    print(f"Title: {result.fields.get('title', {}).value}")
    print(f"Authors: {result.fields.get('authors', {}).value}")
    print(f"Overall confidence: {result.overall_confidence}")
    print(f"Needs review: {result.needs_review}, Warnings: {result.warnings}")


if __name__ == "__main__":
    main()

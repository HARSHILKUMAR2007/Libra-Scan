"""CLI runner for preprocessing and running OCR on an image."""

import argparse
import json
import sys
from pathlib import Path
import cv2
from app.services.ocr import run_ocr
from app.services.preprocess import preprocess


def annotate_image(image, ocr_result):
    """Draw normalized OCR bounding boxes and line IDs on image copy."""
    annotated = image.copy()
    h, w = annotated.shape[:2]
    for line in ocr_result.lines:
        x1, y1, x2, y2 = line.bbox
        pt1 = (int(round(x1 * w)), int(round(y1 * h)))
        pt2 = (int(round(x2 * w)), int(round(y2 * h)))
        cv2.rectangle(annotated, pt1, pt2, (0, 255, 0), 2)
        cv2.putText(annotated, str(line.id), (pt1[0], max(15, pt1[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    return annotated


def main():
    parser = argparse.ArgumentParser(description="Run OCR on an image.")
    parser.add_argument("image_path", type=str, help="Path to input image")
    parser.add_argument("--out", type=str, default="data/samples/out", help="Output directory")
    args = parser.parse_args()

    path = Path(args.image_path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    raw_bytes = path.read_bytes()
    proc_img, meta = preprocess(raw_bytes)
    print(f"Preprocess completed: {meta['processed_width']}x{meta['processed_height']}")

    ocr_result = run_ocr(proc_img)
    lines_json = [line.model_dump() for line in ocr_result.lines]
    print(json.dumps(lines_json, indent=2))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}_ocr.jpg"
    cv2.imwrite(str(out_path), annotate_image(proc_img, ocr_result))
    print(f"Saved annotated OCR image to: {out_path}")


if __name__ == "__main__":
    main()

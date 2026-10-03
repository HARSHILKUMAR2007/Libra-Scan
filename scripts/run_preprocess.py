"""CLI runner for preprocessing single images or directories."""

import argparse
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from app.services.preprocess import fix_orientation, preprocess, validate_and_decode


def make_comparison(orig_bgr: np.ndarray, proc_bgr: np.ndarray) -> np.ndarray:
    """Combine original and processed images side by side normalized to equal height."""
    target_h = min(orig_bgr.shape[0], proc_bgr.shape[0])
    orig_w = int(round(orig_bgr.shape[1] * target_h / orig_bgr.shape[0]))
    proc_w = int(round(proc_bgr.shape[1] * target_h / proc_bgr.shape[0]))
    orig_scaled = cv2.resize(orig_bgr, (orig_w, target_h), interpolation=cv2.INTER_AREA)
    proc_scaled = cv2.resize(proc_bgr, (proc_w, target_h), interpolation=cv2.INTER_AREA)

    cv2.putText(orig_scaled, "original", (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    cv2.putText(proc_scaled, "processed", (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    return np.hstack([orig_scaled, proc_scaled])


def process_single(path: Path, out_dir: Path) -> None:
    """Process a single image file and write outputs."""
    raw = path.read_bytes()
    orig = fix_orientation(validate_and_decode(raw))
    proc, meta = preprocess(raw)

    out_dir.mkdir(parents=True, exist_ok=True)
    proc_path = out_dir / f"{path.stem}_processed.jpg"
    comp_path = out_dir / f"{path.stem}_compare.jpg"

    cv2.imwrite(str(proc_path), proc)
    cv2.imwrite(str(comp_path), make_comparison(orig, proc))
    print(f"Meta: {meta}")
    print(f"Saved: {proc_path} and {comp_path}")


def process_folder(folder: Path) -> None:
    """Process all images in a folder and print a summary per image."""
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = sorted([p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in exts])
    print(f"Found {len(images)} images in {folder}")

    for img_path in images:
        t0 = time.perf_counter()
        try:
            _, meta = preprocess(img_path.read_bytes())
            ms = (time.perf_counter() - t0) * 1000
            print(
                f"{img_path.name}: {meta['original_width']}x{meta['original_height']} -> "
                f"{meta['processed_width']}x{meta['processed_height']} ({ms:.1f}ms)"
            )
        except Exception as exc:
            print(f"{img_path.name}: ERROR - {exc}")


def main() -> None:
    """Entry point for preprocess CLI."""
    parser = argparse.ArgumentParser(description="Run book cover image preprocessing.")
    parser.add_argument("path", type=str, help="Path to an image file or directory")
    parser.add_argument("--out", type=str, default="data/samples/out", help="Output directory for single image runs")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"Error: Path does not exist: {target}", file=sys.stderr)
        sys.exit(1)

    if target.is_file():
        process_single(target, Path(args.out))
    elif target.is_dir():
        process_folder(target)


if __name__ == "__main__":
    main()

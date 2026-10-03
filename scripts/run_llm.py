"""CLI runner for end-to-end preprocessing, OCR, and LLM extraction."""

import argparse
import sys
from pathlib import Path
from app.services.llm import extract_book
from app.services.ocr import run_ocr
from app.services.preprocess import preprocess


def main():
    parser = argparse.ArgumentParser(description="Run Preprocess, OCR, and LLM extraction on a book image.")
    parser.add_argument("image_path", type=str, help="Path to book cover image")
    args = parser.parse_args()

    path = Path(args.image_path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing: {path}")
    proc_img, meta = preprocess(path.read_bytes())
    print(f"Preprocessed: {meta['processed_width']}x{meta['processed_height']}")

    ocr_result = run_ocr(proc_img)
    print(f"OCR found {len(ocr_result.lines)} lines")

    book_details = extract_book(ocr_result)
    print("\n--- Extracted Book Details ---")
    print(book_details.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

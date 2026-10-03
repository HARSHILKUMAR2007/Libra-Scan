"""ISBN validation, extraction, and conversion utilities."""

import re
from typing import Optional

ISBN13_REGEX = re.compile(r"\b(97[89][-\s]*(?:\d[-\s]*){9}\d)\b", re.IGNORECASE)
ISBN10_REGEX = re.compile(r"\b((?:\d[-\s]*){9}[\dX])\b", re.IGNORECASE)


def clean_isbn(raw: str) -> str:
    """Normalize raw ISBN string by stripping whitespace and hyphens."""
    return re.sub(r"[-\s]", "", raw).upper()


def is_valid_isbn10(isbn: str) -> bool:
    """Verify check digit of an ISBN-10 string."""
    cleaned = clean_isbn(isbn)
    if len(cleaned) != 10 or not re.match(r"^\d{9}[\dX]$", cleaned):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(cleaned))
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    """Verify check digit of an ISBN-13 string."""
    cleaned = clean_isbn(isbn)
    if len(cleaned) != 13 or not cleaned.isdigit():
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(cleaned))
    return total % 10 == 0


def isbn10_to_isbn13(isbn10: str) -> Optional[str]:
    """Convert valid ISBN-10 to standard ISBN-13."""
    cleaned = clean_isbn(isbn10)
    if not is_valid_isbn10(cleaned):
        return None
    core = "978" + cleaned[:9]
    check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core)) % 10) % 10
    return f"{core}{check}"


def extract_isbns_from_text(text: str) -> tuple[list[str], list[str]]:
    """Scan arbitrary text and return valid lists of (isbn10_list, isbn13_list)."""
    isbn13_found = []
    for match in ISBN13_REGEX.findall(text):
        cleaned = clean_isbn(match)
        if is_valid_isbn13(cleaned) and cleaned not in isbn13_found:
            isbn13_found.append(cleaned)

    isbn10_found = []
    for match in ISBN10_REGEX.findall(text):
        cleaned = clean_isbn(match)
        if is_valid_isbn10(cleaned) and cleaned not in isbn10_found:
            isbn10_found.append(cleaned)

    return isbn10_found, isbn13_found


def validate_and_sanitize_isbns(isbn10: Optional[str], isbn13: Optional[str]) -> tuple[Optional[str], Optional[str], list[str]]:
    """Validate ISBNs provided by LLM; invalidate bad checksums and create warnings."""
    warnings: list[str] = []
    v10 = clean_isbn(isbn10) if isbn10 else None
    v13 = clean_isbn(isbn13) if isbn13 else None

    if v10:
        if is_valid_isbn10(v10):
            if not v13:
                v13 = isbn10_to_isbn13(v10)
        else:
            warnings.append(f"Extracted ISBN-10 '{isbn10}' failed checksum validation.")
            v10 = None

    if v13 and not is_valid_isbn13(v13):
        warnings.append(f"Extracted ISBN-13 '{isbn13}' failed checksum validation.")
        v13 = None

    return v10, v13, warnings

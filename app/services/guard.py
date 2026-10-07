"""Security guard against prompt injection, jailbreaks, and ungrounded LLM outputs."""

import difflib, re, unicodedata
from datetime import datetime
from app.schemas.book import BookDetails
from app.schemas.ocr import OcrLine
from app.services.isbn import clean_isbn, is_valid_isbn10, is_valid_isbn13
from app.services.preprocess import ImageValidationError

# Constants
MAX_WORDS_PER_IMAGE, MIN_WORDS, MAX_LLM_CHARS, MIN_LINE_HEIGHT, GROUND_THRESHOLD = 400, 3, 3000, 0.005, 0.8
FIELD_LIMITS = {"title": 300, "subtitle": 300, "publisher": 150, "edition": 100, "series": 200, "author": 100}
MAX_AUTHORS = 10

INJECTION_RE = re.compile(
    r"ignore\s+(?:previous|above)\s+instructions|\bdisregard\b|\bsystem\s+prompt\b|"
    r"\byou\s+(?:are|'re)\s+(?:an?|now)\b|\bact\s+as\b|\bjailbreak\b|\bdeveloper\s+mode\b|"
    r"\bapi\s+key\b|^\s*assistant\s*:|^\s*system\s*:|^\s*user\s*:|\boutput\s+json\b|"
    r"\bset\s+(?:the\s+)?title\b|\breveal\b|\bnew\s+instructions\b",
    re.IGNORECASE | re.MULTILINE,
)


class NotABookError(ImageValidationError):
    """Raised when an image does not look like a book cover."""
    def __init__(self, message: str = "This does not look like a book cover"):
        super().__init__(message)


def clean_text(text: str) -> str:
    """Normalize text and strip zero-width, bidi, tag-like fragments, and role markers."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text)
    cleaned = "".join(
        c for c in norm
        if unicodedata.category(c) not in ("Cf", "Cs")
        and not (unicodedata.category(c) == "Cc" and c not in "\t\n")
        and c not in "\u200b\u200c\u200d\u2060\ufeff"
    )
    cleaned = re.sub(r"```+|<[^>]*>|^\s*(?:system|assistant|user):\s*", "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    return re.sub(r"\s+", " ", cleaned).strip()


def filter_lines(lines: list[OcrLine]) -> tuple[list[OcrLine], list[str], bool]:
    """Filter OCR lines removing tiny text, suspicious injection patterns, and role markers."""
    kept, warnings = [], []
    flagged = d_tiny = d_suspicious = False
    for line in lines:
        cleaned = clean_text(line.text)
        if (line.bbox[3] - line.bbox[1]) < MIN_LINE_HEIGHT:
            d_tiny = flagged = True
            continue
        if INJECTION_RE.search(f"{line.text} {cleaned}"):
            d_suspicious = flagged = True
            continue
        if cleaned:
            kept.append(line.model_copy(update={"text": cleaned}))

    if d_tiny:
        warnings.append("Hidden or tiny text ignored")
    if d_suspicious:
        warnings.append("Suspicious instruction-like text removed")
    return kept, warnings, flagged


def check_is_book(lines: list[OcrLine]) -> None:
    """Verify total words and word counts per image are consistent with a book cover."""
    if sum(len(l.text.split()) for l in lines) < MIN_WORDS:
        raise NotABookError()
    images = {l.image for l in lines if l.image} or {"front"}
    if any(sum(len(l.text.split()) for l in lines if l.image == img) > MAX_WORDS_PER_IMAGE for img in images):
        raise NotABookError()


def cap_lines(lines: list[OcrLine]) -> list[OcrLine]:
    """Keep lines in order until total characters reach MAX_LLM_CHARS."""
    kept, total = [], 0
    for l in lines:
        if total + len(l.text) > MAX_LLM_CHARS:
            break
        kept.append(l)
        total += len(l.text)
    return kept


def _is_grounded(val: str, ref: str) -> bool:
    v_norm, r_norm = re.sub(r"[^a-z0-9]", "", val.lower()), re.sub(r"[^a-z0-9]", "", ref.lower())
    if not v_norm or v_norm in r_norm or (len(v_norm) > 4 and r_norm in v_norm):
        return True
    v_toks = [t for t in re.findall(r"\w+", val.lower()) if len(t) > 2]
    r_toks = re.findall(r"\w+", ref.lower())
    if not v_toks:
        v_simple = val.strip().lower()
        return bool(v_simple and v_simple in ref.lower())
    if not r_toks:
        return False
    matched = sum(1 for v in v_toks if any(difflib.SequenceMatcher(None, v, r).ratio() >= GROUND_THRESHOLD for r in r_toks))
    return (matched / len(v_toks)) >= 0.5


def _forbidden(s: str) -> bool:
    return bool(re.search(r"https?://|www\.|\.com/|\[.*?\]\(.*?\)", s, re.I) or "<" in s or ">" in s or "```" in s or any(unicodedata.category(c).startswith("C") for c in s))


def ground_and_validate(details: BookDetails, lines: list[OcrLine]) -> tuple[BookDetails, list[str]]:
    """Ground and validate extracted fields against OCR lines and strict security schemas."""
    warnings, by_id, all_text = [], {l.id: l for l in lines}, " ".join(l.text for l in lines)
    for name in ["title", "subtitle", "publisher", "edition", "series", "year", "language", "isbn10", "isbn13"]:
        f = getattr(details, name, None)
        if not f or f.value in (None, ""):
            continue
        v_str = str(f.value)
        if _forbidden(v_str):
            f.value, f.confidence = None, 0.0
            warnings.append(f"Field {name} removed: invalid characters or format")
        elif name in FIELD_LIMITS and len(v_str) > FIELD_LIMITS[name]:
            f.value, f.confidence = None, 0.0
            warnings.append(f"Field {name} removed: exceeds length limit ({FIELD_LIMITS[name]})")
        elif name == "year":
            if not (isinstance(f.value, int) and 1400 <= f.value <= datetime.now().year):
                f.value, f.confidence = None, 0.0
                warnings.append(f"Field year removed: invalid year {v_str}")
        elif name == "language":
            if not (len(v_str) <= 35 and not re.search(r"[<>{}[\]\\0-9]", v_str)):
                f.value, f.confidence = None, 0.0
                warnings.append("Field language removed: invalid format")
        elif name == "isbn10":
            if not is_valid_isbn10(v_str):
                f.value, f.confidence = None, 0.0
                warnings.append("Field isbn10 removed: invalid checksum")
            else:
                c10 = clean_isbn(v_str)
                all_clean = clean_isbn(all_text)
                is_grounded_isbn = c10 in all_clean or (len(c10) == 10 and c10[:9] in all_clean)
                if not is_grounded_isbn and not _is_grounded(v_str, all_text):
                    f.value, f.confidence = None, 0.0
                    warnings.append(f"Field {name} removed: not found in OCR text")
        elif name == "isbn13":
            if not is_valid_isbn13(v_str):
                f.value, f.confidence = None, 0.0
                warnings.append("Field isbn13 removed: invalid checksum")
            else:
                c13 = clean_isbn(v_str)
                all_clean = clean_isbn(all_text)
                is_grounded_isbn = c13 in all_clean or c13[3:12] in all_clean or (len(c13) >= 8 and c13[-8:] in all_clean)
                if not is_grounded_isbn and not _is_grounded(v_str, all_text):
                    f.value, f.confidence = None, 0.0
                    warnings.append(f"Field {name} removed: not found in OCR text")
        else:
            valid_ids = [i for i in f.source_line_ids if i in by_id]
            ref = " ".join(by_id[i].text for i in valid_ids) if valid_ids else all_text
            is_valid = _is_grounded(v_str, ref) or _is_grounded(v_str, all_text)
            if not is_valid:
                f.value, f.confidence = None, 0.0
                warnings.append(f"Field {name} removed: not found in OCR text")
            elif not valid_ids:
                v_toks = [t for t in re.findall(r"\w+", v_str.lower()) if len(t) > 2]
                matched_ids = [l.id for l in lines if any(t in l.text.lower() for t in v_toks)]
                if matched_ids:
                    f.source_line_ids = matched_ids

    if details.authors and details.authors.value:
        raw = details.authors.value[:MAX_AUTHORS]
        if len(details.authors.value) > MAX_AUTHORS:
            warnings.append(f"Authors list trimmed to {MAX_AUTHORS} entries limit")
        valid_ids = [i for i in details.authors.source_line_ids if i in by_id]
        ref = " ".join(by_id[i].text for i in valid_ids) if valid_ids else all_text
        valid = [
            a.strip() for a in raw
            if not _forbidden(a)
            and len(a) <= FIELD_LIMITS["author"]
            and not re.search(r"[<>{}[\]\\]", a)
            and (_is_grounded(a.strip(), ref) or _is_grounded(a.strip(), all_text))
        ]
        if not valid:
            details.authors.value, details.authors.confidence = None, 0.0
            warnings.append("Field authors removed: not found in OCR text")
        else:
            details.authors.value = valid
            if not valid_ids:
                all_a_toks = [t for a in valid for t in re.findall(r"\w+", a.lower()) if len(t) > 2]
                matched_ids = [l.id for l in lines if any(t in l.text.lower() for t in all_a_toks)]
                if matched_ids:
                    details.authors.source_line_ids = matched_ids
    return details, warnings

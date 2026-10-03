"""LLM service extracting structured book metadata from OCR text."""

import logging
from pathlib import Path
from typing import Optional, Union

from app.core.config import get_settings
from app.schemas.book import BookDetails
from app.schemas.ocr import OcrLine, OcrResult

logger = logging.getLogger(__name__)
PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "extract_book.txt"


def format_position(line: OcrLine) -> str:
    """Format spatial position and relative height descriptor for an OCR line."""
    x1, y1, x2, y2 = line.bbox
    yc, xc, h = (y1 + y2) / 2, (x1 + x2) / 2, y2 - y1
    v_pos = "top" if yc < 0.33 else ("middle" if yc <= 0.66 else "bottom")
    h_pos = "left" if xc < 0.33 else ("center" if xc <= 0.66 else "right")
    size = "small" if h < 0.04 else ("medium" if h <= 0.08 else "large")
    return f"{v_pos}, {h_pos}, {size}"


def build_ocr_text(lines: list[OcrLine]) -> str:
    """Render compact list of OCR lines formatted as id | text | position."""
    if not lines:
        return "No text detected."
    return "\n".join(f"{line.id} | {line.text} | {format_position(line)}" for line in lines)


def build_prompt_ocr_block(front_lines: list[OcrLine], back_lines: Optional[list[OcrLine]] = None) -> str:
    """Render combined prompt text block with section headers for front and back covers."""
    sections = ["=== FRONT COVER ==="]
    sections.append(build_ocr_text(front_lines))
    if back_lines is not None:
        sections.append("=== BACK COVER ===")
        sections.append(build_ocr_text(back_lines))
    return "\n".join(sections)


def _call_gemini(prompt: str, model_name: str, api_key: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    res = client.models.generate_content(
        model=model_name, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return res.text or "{}"


def _call_openai(prompt: str, model_name: str, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    res = client.chat.completions.create(
        model=model_name, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
    )
    return res.choices[0].message.content or "{}"


def extract_book(ocr_input: Union[OcrResult, list[OcrLine], str], isbn_hint: str = "") -> BookDetails:
    """Extract book details from OCR results using configured LLM provider."""
    settings = get_settings()
    template = PROMPT_FILE.read_text(encoding="utf-8")

    if isinstance(ocr_input, str):
        ocr_text = ocr_input
    elif isinstance(ocr_input, OcrResult):
        ocr_text = build_ocr_text(ocr_input.lines)
    else:
        ocr_text = build_ocr_text(ocr_input)

    hint_text = f"HINT: Valid ISBN detected on back cover: {isbn_hint}" if isbn_hint else ""
    prompt = template.replace("{ocr_lines}", ocr_text).replace("{isbn_hint}", hint_text)

    provider = settings.LLM_PROVIDER.lower()
    last_err = None

    for attempt in range(2):
        try:
            if provider == "gemini":
                if not settings.GEMINI_API_KEY:
                    raise ValueError("GEMINI_API_KEY is not configured")
                raw = _call_gemini(prompt, settings.LLM_MODEL, settings.GEMINI_API_KEY)
            elif provider == "openai":
                if not settings.OPENAI_API_KEY:
                    raise ValueError("OPENAI_API_KEY is not configured")
                raw = _call_openai(prompt, settings.LLM_MODEL, settings.OPENAI_API_KEY)
            else:
                raise ValueError(f"Unsupported LLM provider: {provider}")

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return BookDetails.model_validate_json(cleaned)
        except Exception as exc:
            last_err = exc
            logger.warning("LLM extraction attempt %d failed: %s", attempt + 1, exc)

    raise ValueError(f"LLM extraction failed after retry: {last_err}")

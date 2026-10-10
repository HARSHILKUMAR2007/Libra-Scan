# LibraScan

> **Scan a cover. Catalog a book.**

LibraScan is an automated book cataloging system that extracts metadata from book cover photos (front and back) using Azure Document Intelligence OCR and LLM intelligence (Google Gemini / OpenAI).

## Features

- **Cover Scanning & OCR**: Upload front (and optional back) covers with automatic orientation correction, contrast enhancement, and bounding box mapping.
- **Bulk Upload & Queue**: Upload multiple book covers at once with choice of **Front only** or **Front + Back** auto-pairing and live queue tracking.
- **Verification Studio**: Interactive dual-cover viewer with side-by-side OCR bounding boxes and field-level confidence badges.
- **Catalog & Review Queue**: SQLite-backed catalog with CSV export, search, and priority sorting for books needing librarian review.
- **Analytics Dashboard**: Real-time stats on catalog size, 30-day activity trends, verification breakdown, and field extraction accuracy.

## Getting Started

### 1. Prerequisites
- Python 3.11+
- Virtual environment tool (e.g. `venv`)

### 2. Setup Environment
```bash
# Clone the repository
git clone https://github.com/darshil2032007/Libra-Scan
cd book-ocr

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure `.env`
Copy `.env.example` to `.env` and fill in your API credentials:
```bash
cp .env.example .env
```
Required keys:
- `AZURE_DI_ENDPOINT` & `AZURE_DI_KEY`: Azure Document Intelligence resource.
- `GEMINI_API_KEY` (or `OPENAI_API_KEY`): LLM provider for metadata extraction.

### 4. Run Application
```bash
uvicorn app.main:app --reload
```
Open your browser at `http://127.0.0.1:8000`.

## Testing
Run the Python test suite:
```bash
pytest
```
Run frontend unit tests:
```bash
node --test tests/test_pairing.mjs
```

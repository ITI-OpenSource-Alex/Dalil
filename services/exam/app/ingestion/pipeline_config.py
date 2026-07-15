"""
app/ingestion/pipeline_config.py
---------------------------------
Shared constants and helpers for the stage-based ingestion pipeline.

Used by:
  - scripts/ocr_books.py   (Stage 1)
  - scripts/parse_books.py  (Stage 2)
  - scripts/ingest_books.py (Stage 3)
  - scripts/validate_books.py (Stage 4)
  - scripts/pipeline.py     (orchestrator)
"""

from __future__ import annotations

import re
from pathlib import Path

# Project root — two levels up from app/ingestion/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SAMPLE_BOOKS_DIR = BASE_DIR / "data" / "sample_books"
OCR_DIR = BASE_DIR / "data" / "ocr"
PARSED_DIR = BASE_DIR / "data" / "parsed"

SKILLS = ["reading", "listening", "writing", "speaking"]


def slugify_book(name: str) -> str:
    """Convert a book directory name to a short slug.

    Examples
    --------
    >>> slugify_book("IELTS 14 Academic")
    'IELTS14'
    >>> slugify_book("IELTS 19 Academic")
    'IELTS19'
    """
    m = re.search(r"IELTS\s*(\d+)", name, re.IGNORECASE)
    if m:
        return f"IELTS{m.group(1)}"
    # Fallback: strip spaces and non-alphanum
    return re.sub(r"[^A-Za-z0-9]+", "", name)


def discover_pdfs(data_dir: Path | None = None) -> list[tuple[Path, str]]:
    """Discover book PDFs and return (path, slug) pairs.

    Only includes PDFs > 100 KB (skips tiny files that are not real books).
    Returns results sorted by slug.
    """
    root = data_dir or SAMPLE_BOOKS_DIR
    results: list[tuple[Path, str]] = []
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.stat().st_size < 100_000:
            continue
        # Use the immediate parent directory as the book name
        book_dir_name = pdf.parent.name
        slug = slugify_book(book_dir_name)
        results.append((pdf, slug))
    return results


def discover_ocr_texts(
    ocr_dir: Path | None = None,
    *,
    book: str | None = None,
) -> list[tuple[Path, str]]:
    """Discover OCR text files and return (path, slug) pairs.

    Parameters
    ----------
    book : str | None
        If provided, only return files for this book slug.
    """
    root = ocr_dir or OCR_DIR
    if not root.exists():
        return []
    results: list[tuple[Path, str]] = []
    for txt in sorted(root.rglob("*.txt")):
        slug = txt.parent.name
        if book and slug != book:
            continue
        results.append((txt, slug))
    return results


def discover_parsed_json(
    parsed_dir: Path | None = None,
    *,
    book: str | None = None,
    skill: str | None = None,
    test: int | None = None,
) -> list[Path]:
    """Discover parsed JSON files with optional filtering.

    Directory structure: parsed/<BookSlug>/<skill>/test<N>.json
    """
    root = parsed_dir or PARSED_DIR
    if not root.exists():
        return []
    results: list[Path] = []
    for json_file in sorted(root.rglob("*.json")):
        if json_file.name == "metadata.json":
            continue
        # Expected: parsed/IELTS14/reading/test1.json
        parts = json_file.relative_to(root).parts
        if len(parts) != 3:
            continue
        file_slug, file_skill, file_name = parts
        if book and file_slug != book:
            continue
        if skill and file_skill != skill:
            continue
        if test:
            m = re.match(r"test(\d+)\.json", file_name)
            if m and int(m.group(1)) != test:
                continue
        results.append(json_file)
    return results

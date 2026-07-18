"""
Stage 1 — OCR
==============
PDF → TXT

Discovers Cambridge IELTS PDFs under ``data/sample_books/``, extracts text
using pdfplumber + OCR fallback, and writes plain-text files under ``data/ocr/``.

Each book gets its own directory with a single ``full.txt`` and a ``full.sha256``
sidecar.  Re-running skips books whose PDF hash has not changed.

Output layout::

    data/ocr/
        IELTS14/
            full.txt
            full.sha256
        IELTS15/
            full.txt
            full.sha256

Usage::

    python scripts/ocr_books.py
    python scripts/ocr_books.py --book IELTS14
    python scripts/ocr_books.py --force
    python scripts/ocr_books.py --data-dir ./my_books
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingestion.ocr_service import OcrService
from app.ingestion.pipeline_config import (
    OCR_DIR,
    SAMPLE_BOOKS_DIR,
    discover_pdfs,
)


def _read_sha256(sha_path: Path) -> str | None:
    """Read the stored SHA-256 hash from a sidecar file."""
    if sha_path.exists():
        return sha_path.read_text(encoding="utf-8").strip()
    return None


def _write_sha256(sha_path: Path, hash_value: str) -> None:
    """Write a SHA-256 hash to a sidecar file."""
    sha_path.parent.mkdir(parents=True, exist_ok=True)
    sha_path.write_text(hash_value + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 1: Extract text from Cambridge IELTS PDFs (OCR).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=SAMPLE_BOOKS_DIR,
        help="Root directory containing book PDFs.",
    )
    parser.add_argument(
        "--ocr-dir",
        type=Path,
        default=OCR_DIR,
        help="Output directory for OCR text files.",
    )
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="Process only this book slug (e.g. IELTS14).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-OCR even if the PDF hash has not changed.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("STAGE 1: OCR — PDF → TXT")
    print("=" * 70)
    print(f"  Source:  {args.data_dir}")
    print(f"  Output:  {args.ocr_dir}")
    if args.book:
        print(f"  Book:    {args.book}")
    if args.force:
        print("  Force:   yes")
    print()

    pdfs = discover_pdfs(args.data_dir)
    if args.book:
        pdfs = [(p, s) for p, s in pdfs if s == args.book]

    if not pdfs:
        print("[WARN] No PDFs found.")
        return 1

    print(f"Found {len(pdfs)} PDF(s):")
    for pdf_path, slug in pdfs:
        size_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"  {slug}: {pdf_path.name} ({size_mb:.1f} MB)")
    print()

    ocr_service = OcrService()
    results: list[dict] = []
    errors: list[str] = []

    try:
        from tqdm import tqdm
        pdf_iter = tqdm(pdfs, desc="OCR", unit="book")
    except ImportError:
        pdf_iter = pdfs

    for pdf_path, slug in pdf_iter:
        book_dir = args.ocr_dir / slug
        txt_path = book_dir / "full.txt"
        sha_path = book_dir / "full.sha256"

        current_hash = OcrService.compute_hash(pdf_path)

        # Skip if hash matches and not forced
        if not args.force:
            stored_hash = _read_sha256(sha_path)
            if stored_hash == current_hash:
                print(f"  [SKIP] {slug} — PDF unchanged (hash: {current_hash})")
                results.append({"slug": slug, "status": "skipped"})
                continue

        print(f"  [OCR]  {slug} — processing {pdf_path.name}...")
        t0 = time.time()

        try:
            text = ocr_service.extract(pdf_path)
            elapsed = time.time() - t0

            book_dir.mkdir(parents=True, exist_ok=True)
            txt_path.write_text(text, encoding="utf-8")
            _write_sha256(sha_path, current_hash)

            line_count = len(text.splitlines())
            char_count = len(text)
            print(f"         Done: {line_count} lines, {char_count} chars [{elapsed:.1f}s]")
            results.append({"slug": slug, "status": "processed", "time": elapsed})

        except Exception as e:
            elapsed = time.time() - t0
            print(f"         [ERROR] {e} [{elapsed:.1f}s]")
            errors.append(f"{slug}: {e}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    processed = sum(1 for r in results if r["status"] == "processed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    print(f"  Processed: {processed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {len(errors)}")

    if errors:
        print()
        print("ERRORS:")
        for err in errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

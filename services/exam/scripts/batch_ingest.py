"""
Batch Ingestion Pipeline
------------------------
Discovers Cambridge IELTS PDFs under ``data/sample_books/``, parses them with
the appropriate skill-area parser, and upserts into the database.

Resumability comes from two layers:
  1. **OCR cache** — per-page text is cached on disk, so re-running after a
     crash skips pages that were already OCR'd.
  2. **DB idempotency** — ``upsert_question`` checks ``(book_ref, test_number,
     skill_area)`` before inserting, so already-ingested records are skipped.

Usage (inside Docker):
    python scripts/batch_ingest.py

Environment variables:
    DATABASE_URL     — asyncpg connection string (default: postgres://goa:goa_pass@postgres:5432/exam_db)
    DATA_DIR         — root directory containing PDFs (default: ./data/sample_books)
    OCR_CACHE_DIR    — where to store cached OCR page text (default: ./.cache/ocr)
    SKILLS           — comma-separated list of skills to ingest (default: reading,writing,speaking)
    DRY_RUN          — set to "1" to parse without writing to DB
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from app.ingestion.reading_parser import ReadingParser
from app.ingestion.listening_parser import ListeningParser
from app.ingestion.writing_parser import WritingParser
from app.ingestion.speaking_parser import SpeakingParser

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://goa:goa_pass@postgres:5432/exam_db",
)

DATA_DIR = Path(
    os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_books"),
    )
)

MIGRATIONS_DIR = Path(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "migrations")
)

SKILLS = os.getenv("SKILLS", "reading,writing,speaking").split(",")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

PARSERS = {
    "reading": ReadingParser(),
    "listening": ListeningParser(),
    "writing": WritingParser(),
    "speaking": SpeakingParser(),
}


async def run_migrations(pool: asyncpg.Pool) -> None:
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with pool.acquire() as conn:
        for mig in migrations:
            sql = mig.read_text(encoding="utf-8")
            try:
                await conn.execute(sql)
                print(f"  [OK] {mig.name}")
            except Exception as e:
                if "already exists" in str(e) or "duplicate" in str(e).lower():
                    print(f"  [SKIP] {mig.name} (already applied)")
                else:
                    print(f"  [WARN] {mig.name}: {e}")


async def upsert_question(pool: asyncpg.Pool, payload: dict) -> dict | None:
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM questions WHERE book_ref=$1 AND test_number=$2 AND skill_area=$3 LIMIT 1",
            payload["book_ref"], payload["test_number"], payload["skill_area"],
        )
        if existing:
            return None

        record = await conn.fetchrow(
            """INSERT INTO questions (book_ref, test_number, exam_type, skill_area,
               passage_text, audio_s3_key, questions, answer_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
               RETURNING id""",
            payload["book_ref"],
            payload["test_number"],
            payload.get("exam_type", "academic"),
            payload.get("skill_area", "reading"),
            payload.get("passage_text"),
            payload.get("audio_s3_key"),
            json.dumps(payload.get("questions", [])),
            json.dumps(payload.get("answer_key", {})),
        )
        return dict(record) if record else None


def discover_pdfs(data_dir: Path) -> list[Path]:
    pdfs = sorted(data_dir.rglob("*.pdf"))
    return [p for p in pdfs if p.stat().st_size > 100_000]


async def main() -> int:
    print("=" * 70)
    print("BATCH INGESTION PIPELINE")
    print("=" * 70)
    print(f"  Data dir:   {DATA_DIR}")
    print(f"  Database:   {DATABASE_URL}")
    print(f"  Skills:     {', '.join(SKILLS)}")
    print(f"  Dry run:    {DRY_RUN}")
    print()

    pdfs = discover_pdfs(DATA_DIR)
    if not pdfs:
        print(f"[WARN] No PDFs found in {DATA_DIR}")
        return 1

    print(f"Found {len(pdfs)} PDF(s):")
    for pdf in pdfs:
        size_mb = pdf.stat().st_size / (1024 * 1024)
        print(f"  {pdf.relative_to(DATA_DIR)} ({size_mb:.1f} MB)")
    print()

    pool = None
    if not DRY_RUN:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        print("--- Running migrations ---")
        await run_migrations(pool)
        print()

    results: list[dict] = []
    errors: list[str] = []

    for pdf in pdfs:
        for skill in SKILLS:
            parser = PARSERS.get(skill)
            if not parser:
                continue

            label = f"{pdf.stem} / {skill}"
            print(f"--- {label} ---")
            t0 = time.time()

            try:
                parsed = parser.parse_pdf(pdf)
                elapsed = time.time() - t0
                q_count = len(parsed.get("questions", []))
                ak_count = len(parsed.get("answer_key", {}))

                print(f"  Parsed: {parsed['book_ref']} Test {parsed['test_number']} "
                      f"({parsed['exam_type']}) — {q_count} questions, "
                      f"{ak_count} answer keys [{elapsed:.1f}s]")

                if DRY_RUN:
                    results.append({"label": label, "questions": q_count, "status": "dry_run"})
                elif pool:
                    record = await upsert_question(pool, parsed)
                    if record:
                        print(f"  [DB] Inserted as {record['id']}")
                        results.append({"label": label, "questions": q_count, "status": "inserted"})
                    else:
                        print("  [DB] Already exists — skipped")
                        results.append({"label": label, "questions": q_count, "status": "skipped"})

            except Exception as e:
                elapsed = time.time() - t0
                print(f"  [ERROR] {e} [{elapsed:.1f}s]")
                errors.append(f"{label}: {e}")

            print()

    if pool:
        await pool.close()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total PDFs:   {len(pdfs)}")
    print(f"  Processed:    {len(results)}")
    print(f"  Errors:       {len(errors)}")

    for r in results:
        status_icon = {"inserted": "+", "skipped": "=", "dry_run": "~"}.get(r["status"], "?")
        print(f"  [{status_icon}] {r['label']}: {r['questions']} questions")

    if errors:
        print()
        print("ERRORS:")
        for err in errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

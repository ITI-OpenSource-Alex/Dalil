"""
Stage 3 — Ingest
=================
JSON → PostgreSQL

Reads parsed JSON files from ``data/parsed/`` and inserts them into the
database using the existing ``QuestionRepository``.

No OCR code.  No parser code.

Usage::

    python scripts/ingest_books.py
    python scripts/ingest_books.py --book IELTS14
    python scripts/ingest_books.py --book IELTS14 --skill reading --test 1
    python scripts/ingest_books.py --dry-run

Environment variables::

    DATABASE_URL — asyncpg connection string (required)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingestion.pipeline_config import (
    PARSED_DIR,
    SKILLS,
    discover_parsed_json,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://goa:goa_pass@postgres:5432/exam_db",
)

MIGRATIONS_DIR = Path(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "migrations")
)


async def run_migrations(pool) -> None:
    """Run all SQL migrations in order."""
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


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 3: Ingest parsed JSON into PostgreSQL.",
    )
    parser.add_argument(
        "--parsed-dir",
        type=Path,
        default=PARSED_DIR,
        help="Directory containing parsed JSON files.",
    )
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="Ingest only this book slug (e.g. IELTS14).",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        choices=SKILLS,
        help="Ingest only this skill area.",
    )
    parser.add_argument(
        "--test",
        type=int,
        default=None,
        help="Ingest only this test number.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and validate JSON without writing to database.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("STAGE 3: INGEST — JSON → PostgreSQL")
    print("=" * 70)
    print(f"  Source:    {args.parsed_dir}")
    print(f"  Database:  {DATABASE_URL}")
    if args.book:
        print(f"  Book:      {args.book}")
    if args.skill:
        print(f"  Skill:     {args.skill}")
    if args.test:
        print(f"  Test:      {args.test}")
    if args.dry_run:
        print("  Dry run:   yes")
    print()

    json_files = discover_parsed_json(
        args.parsed_dir, book=args.book, skill=args.skill, test=args.test
    )

    if not json_files:
        print("[ERROR] No parsed JSON files found. Run parse_books.py first.")
        return 1

    print(f"Found {len(json_files)} JSON file(s) to ingest.")
    print()

    import asyncpg
    from app.repositories.question_repository import QuestionRepository

    pool = None
    if not args.dry_run:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        print("--- Running migrations ---")
        await run_migrations(pool)
        print()

    repo = QuestionRepository(pool) if pool else None
    results: list[dict] = []
    errors: list[str] = []

    for json_path in json_files:
        parts = json_path.relative_to(args.parsed_dir).parts
        label = "/".join(parts)

        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            q_count = len(payload.get("questions", []))
            ak_count = len(payload.get("answer_key", {}))

            if args.dry_run:
                print(f"  [DRY] {label}: {q_count} questions, {ak_count} answers")
                results.append({"label": label, "status": "dry_run", "questions": q_count})
            elif repo:
                record = await repo.upsert_question(payload)
                record_id = record.get("id") if isinstance(record, dict) else None
                if record_id and record_id != payload.get("id"):
                    print(f"  [+] {label}: {q_count} questions → id={str(record_id)[:8]}...")
                    results.append({"label": label, "status": "inserted", "questions": q_count})
                else:
                    print(f"  [=] {label}: already exists — skipped")
                    results.append({"label": label, "status": "skipped", "questions": q_count})

        except Exception as e:
            print(f"  [!] {label}: {e}")
            errors.append(f"{label}: {e}")

    if pool:
        await pool.close()

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    inserted = sum(1 for r in results if r["status"] == "inserted")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    dry_run = sum(1 for r in results if r["status"] == "dry_run")
    total_q = sum(r.get("questions", 0) for r in results)
    print(f"  Inserted:  {inserted}")
    print(f"  Skipped:   {skipped}")
    if dry_run:
        print(f"  Dry run:   {dry_run}")
    print(f"  Questions: {total_q} total")
    print(f"  Errors:    {len(errors)}")

    if errors:
        print()
        print("ERRORS:")
        for err in errors:
            print(f"  - {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

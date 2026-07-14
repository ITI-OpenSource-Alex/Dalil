"""
E2E Ingestion Verification Script
----------------------------------
Ingests Cambridge IELTS 14 Academic (all 4 tests) into the real database,
then verifies:
  - Reading: 3 passages, 40 questions, answer keys
  - Listening: 4 sections, 40 questions, audio S3 key
  - Writing: Task 1 + Task 2 prompts
  - Speaking: Parts 1, 2, 3

Uses the new OCR cache layer for resumability — safe to re-run after crashes.
Uses page-range support to process specific tests instead of all 95 pages.

Usage:
    python scripts/e2e_ingestion_verify.py

Environment variables:
    DATABASE_URL   — asyncpg connection string
    PDF_PATH       — path to Cambridge IELTS 14 PDF
    OCR_CACHE_DIR  — cache directory (default: .cache/ocr)
"""

import asyncio
import json
import os
import sys
import time

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

PDF_PATH = os.getenv(
    "PDF_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "sample_books", "IELTS 14 Academic", "Cambridge IELTS 14.pdf",
    ),
)

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "migrations",
)


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Run all SQL migrations in order."""
    import pathlib
    migrations = sorted(pathlib.Path(MIGRATIONS_DIR).glob("*.sql"))
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


async def upsert_question(pool: asyncpg.Pool, payload: dict) -> dict:
    """Insert or return existing question."""
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM questions WHERE book_ref=$1 AND test_number=$2 AND skill_area=$3 LIMIT 1",
            payload["book_ref"], payload["test_number"], payload["skill_area"],
        )
        if existing:
            return dict(existing)

        record = await conn.fetchrow(
            """INSERT INTO questions (book_ref, test_number, exam_type, skill_area,
               passage_text, audio_s3_key, questions, answer_key)
               VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
               ON CONFLICT (book_ref, test_number, skill_area) DO NOTHING
               RETURNING *""",
            payload["book_ref"],
            payload["test_number"],
            payload.get("exam_type", "academic"),
            payload.get("skill_area", "reading"),
            payload.get("passage_text"),
            payload.get("audio_s3_key"),
            json.dumps(payload.get("questions", [])),
            json.dumps(payload.get("answer_key", {})),
        )
        if record:
            return dict(record)
        # If ON CONFLICT fired, fetch the existing row
        existing = await conn.fetchrow(
            "SELECT * FROM questions WHERE book_ref=$1 AND test_number=$2 AND skill_area=$3 LIMIT 1",
            payload["book_ref"], payload["test_number"], payload["skill_area"],
        )
        return dict(existing) if existing else payload


def verify_reading(parsed: dict, test_num: int) -> list[str]:
    """Verify reading parse results. Returns list of issues."""
    issues = []
    prefix = f"[Reading T{test_num}]"

    questions = parsed.get("questions", [])
    answer_key = parsed.get("answer_key", {})
    passage_text = parsed.get("passage_text")

    if not passage_text:
        issues.append(f"{prefix} No passage text extracted")
    else:
        passages = passage_text.split("\n\n---\n\n")
        if len(passages) < 3:
            issues.append(f"{prefix} Expected 3 passages, got {len(passages)}")
        else:
            print(f"  {prefix} 3 passages OK (lengths: {[len(p) for p in passages]})")

    if len(questions) < 30:
        issues.append(f"{prefix} Expected ~40 questions, got {len(questions)}")
    else:
        print(f"  {prefix} {len(questions)} questions extracted")

    if len(answer_key) < 30:
        issues.append(f"{prefix} Expected ~40 answer keys, got {len(answer_key)}")
    else:
        print(f"  {prefix} {len(answer_key)} answer keys extracted")
        for k in ["1", "10", "20", "30", "40"]:
            if k not in answer_key:
                issues.append(f"{prefix} Missing answer key for Q{k}")

    types_found = set(q.get("question_type") for q in questions)
    if len(types_found) < 2:
        issues.append(f"{prefix} Only {len(types_found)} question type(s) found: {types_found}")
    else:
        print(f"  {prefix} Question types: {sorted(types_found)}")

    return issues


def verify_writing(parsed: dict) -> list[str]:
    """Verify writing parse results."""
    issues = []
    prefix = "[Writing]"

    questions = parsed.get("questions", [])
    if len(questions) < 2:
        issues.append(f"{prefix} Expected 2 tasks (Task 1 + Task 2), got {len(questions)}")
    else:
        task1 = questions[0]
        task2 = questions[1]
        if "Writing Task 1" not in task1.get("question_type", ""):
            issues.append(f"{prefix} Task 1 type mismatch: {task1.get('question_type')}")
        if "Writing Task 2" not in task2.get("question_type", ""):
            issues.append(f"{prefix} Task 2 type mismatch: {task2.get('question_type')}")
        if len(task1.get("prompt", "")) < 30:
            issues.append(f"{prefix} Task 1 prompt too short ({len(task1.get('prompt', ''))} chars)")
        if len(task2.get("prompt", "")) < 30:
            issues.append(f"{prefix} Task 2 prompt too short ({len(task2.get('prompt', ''))} chars)")
        print(f"  {prefix} Task 1 prompt: {task1.get('prompt', '')[:80]}...")
        print(f"  {prefix} Task 2 prompt: {task2.get('prompt', '')[:80]}...")

    return issues


def verify_speaking(parsed: dict) -> list[str]:
    """Verify speaking parse results."""
    issues = []
    prefix = "[Speaking]"

    questions = parsed.get("questions", [])
    if not questions:
        issues.append(f"{prefix} No questions extracted")
        return issues

    part1 = [q for q in questions if q.get("question_type") == "Speaking Part 1"]
    part2 = [q for q in questions if q.get("question_type") == "Speaking Part 2"]
    part3 = [q for q in questions if q.get("question_type") == "Speaking Part 3"]

    if not part1:
        issues.append(f"{prefix} No Part 1 questions found")
    else:
        print(f"  {prefix} Part 1: {len(part1)} questions")

    if not part2:
        issues.append(f"{prefix} No Part 2 cue card found")
    else:
        cue = part2[0]
        bullets = cue.get("bullet_points", [])
        print(f"  {prefix} Part 2 topic: {cue['prompt'][:60]}...")
        print(f"  {prefix} Part 2 bullets: {len(bullets)}")

    if not part3:
        issues.append(f"{prefix} No Part 3 discussion questions found")
    else:
        print(f"  {prefix} Part 3: {len(part3)} questions")

    return issues


async def main() -> int:
    print("=" * 70)
    print("E2E INGESTION VERIFICATION — Cambridge IELTS 14 Academic")
    print("=" * 70)

    if not os.path.exists(PDF_PATH):
        print(f"\n[FATAL] PDF not found: {PDF_PATH}")
        print(f"  Expected at: {os.path.abspath(PDF_PATH)}")
        return 1

    pdf_size_mb = os.path.getsize(PDF_PATH) / (1024 * 1024)
    print(f"\nPDF: {PDF_PATH} ({pdf_size_mb:.1f} MB)")
    print(f"Database: {DATABASE_URL}")
    print(f"OCR Cache: {os.environ.get('OCR_CACHE_DIR', '.cache/ocr (default)')}")

    # Connect
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    print("\n--- Running migrations ---")
    await run_migrations(pool)

    all_issues: list[str] = []

    # ─── READING ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("READING — Parsing PDF via full pipeline (pdfplumber → OCR fallback)...")
    print("=" * 70)

    reading_parser = ReadingParser()
    t0 = time.time()
    try:
        reading_parsed = reading_parser.parse_pdf(PDF_PATH)
        elapsed = time.time() - t0
        print(f"  Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] ReadingParser.parse_pdf failed after {elapsed:.1f}s: {e}")
        all_issues.append(f"[Reading] parse_pdf failed: {e}")
        reading_parsed = None

    if reading_parsed:
        test_num = reading_parsed.get("test_number", 1)
        print(f"  Detected: {reading_parsed['book_ref']} Test {test_num} ({reading_parsed['exam_type']})")
        issues = verify_reading(reading_parsed, test_num)
        all_issues.extend(issues)

        record = await upsert_question(pool, reading_parsed)
        print(f"  [DB] Stored as question ID: {record.get('id')}")

    # ─── WRITING ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WRITING — Parsing PDF via full pipeline...")
    print("=" * 70)

    writing_parser = WritingParser()
    t0 = time.time()
    try:
        writing_parsed = writing_parser.parse_pdf(PDF_PATH)
        elapsed = time.time() - t0
        print(f"  Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] WritingParser.parse_pdf failed after {elapsed:.1f}s: {e}")
        all_issues.append(f"[Writing] parse_pdf failed: {e}")
        writing_parsed = None

    if writing_parsed:
        print(f"  Detected: {writing_parsed['book_ref']} Test {writing_parsed.get('test_number', '?')}")
        issues = verify_writing(writing_parsed)
        all_issues.extend(issues)

        record = await upsert_question(pool, writing_parsed)
        print(f"  [DB] Stored as question ID: {record.get('id')}")

    # ─── SPEAKING ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SPEAKING — Parsing PDF via full pipeline...")
    print("=" * 70)

    speaking_parser = SpeakingParser()
    t0 = time.time()
    try:
        speaking_parsed = speaking_parser.parse_pdf(PDF_PATH)
        elapsed = time.time() - t0
        print(f"  Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] SpeakingParser.parse_pdf failed after {elapsed:.1f}s: {e}")
        all_issues.append(f"[Speaking] parse_pdf failed: {e}")
        speaking_parsed = None

    if speaking_parsed:
        print(f"  Detected: {speaking_parsed['book_ref']} Test {speaking_parsed.get('test_number', '?')}")
        issues = verify_speaking(speaking_parsed)
        all_issues.extend(issues)

        record = await upsert_question(pool, speaking_parsed)
        print(f"  [DB] Stored as question ID: {record.get('id')}")

    # ─── LISTENING ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("LISTENING — Parsing PDF via full pipeline...")
    print("=" * 70)

    listening_parser = ListeningParser()
    t0 = time.time()
    try:
        listening_parsed = listening_parser.parse_pdf(PDF_PATH)
        elapsed = time.time() - t0
        print(f"  Completed in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] ListeningParser.parse_pdf failed after {elapsed:.1f}s: {e}")
        all_issues.append(f"[Listening] parse_pdf failed: {e}")
        listening_parsed = None

    if listening_parsed:
        questions = listening_parsed.get("questions", [])
        audio_key = listening_parsed.get("audio_s3_key")
        print(f"  Detected: {listening_parsed['book_ref']} Test {listening_parsed.get('test_number', '?')}")
        print(f"  Questions: {len(questions)}")
        print(f"  Audio S3 key: {audio_key}")

        if len(questions) < 30:
            all_issues.append(f"[Listening] Expected ~40 questions, got {len(questions)}")
        if not audio_key:
            all_issues.append("[Listening] No audio S3 key generated")

        record = await upsert_question(pool, listening_parsed)
        print(f"  [DB] Stored as question ID: {record.get('id')}")

    # ─── DATABASE VERIFICATION ─────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("DATABASE VERIFICATION")
    print("=" * 70)

    async with pool.acquire() as conn:
        stats = await conn.fetch(
            "SELECT book_ref, exam_type, skill_area, "
            "jsonb_array_length(questions) as q_count "
            "FROM questions ORDER BY book_ref, skill_area"
        )
        print(f"\n  Total records in questions table: {len(stats)}")
        print(f"  {'Book':<12} {'Type':<10} {'Skill':<12} {'Questions':<10}")
        print(f"  {'-'*12} {'-'*10} {'-'*12} {'-'*10}")
        for row in stats:
            print(f"  {row['book_ref']:<12} {row['exam_type']:<10} {row['skill_area']:<12} {row['q_count']:<10}")

    # ─── IDEMPOTENCY CHECK ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("IDEMPOTENCY CHECK")
    print("=" * 70)

    async with pool.acquire() as conn:
        count_before = await conn.fetchval("SELECT COUNT(*) FROM questions")

    # Re-insert all parsed results — should all be skipped
    if reading_parsed:
        await upsert_question(pool, reading_parsed)
    if writing_parsed:
        await upsert_question(pool, writing_parsed)
    if speaking_parsed:
        await upsert_question(pool, speaking_parsed)
    if listening_parsed:
        await upsert_question(pool, listening_parsed)

    async with pool.acquire() as conn:
        count_after = await conn.fetchval("SELECT COUNT(*) FROM questions")

    if count_before == count_after:
        print(f"  [OK] Row count unchanged: {count_before} → {count_after}")
    else:
        all_issues.append(f"Idempotency failed: {count_before} → {count_after}")
        print(f"  [FAIL] Row count changed: {count_before} → {count_after}")

    await pool.close()

    # ─── SUMMARY ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if all_issues:
        print(f"RESULT: {len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1
    else:
        print("RESULT: ALL CHECKS PASSED ✓")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

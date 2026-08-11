"""
Stage 2 — Parse
================
TXT → JSON

Reads OCR text files from ``data/ocr/``, runs the appropriate skill parser,
and writes normalized JSON under ``data/parsed/``.

No OCR code.  No database code.

Output layout::

    data/parsed/
        IELTS14/
            metadata.json
            reading/
                test1.json
                test2.json
                test3.json
                test4.json
            listening/
                test1.json
                ...
            writing/
                test1.json
                ...
            speaking/
                test1.json
                ...

Usage::

    python scripts/parse_books.py
    python scripts/parse_books.py --book IELTS14
    python scripts/parse_books.py --book IELTS14 --skill reading --test 1
    python scripts/parse_books.py --force
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import boto3

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingestion.pipeline_config import (
    OCR_DIR,
    PARSED_DIR,
    SKILLS,
    discover_ocr_texts,
)
from app.ingestion.ocr_normalizer import DEFAULT_NORMALIZER
from app.ingestion.reading_parser import ReadingParser
from app.ingestion.listening_parser import ListeningParser
from app.ingestion.writing_parser import WritingParser
from app.ingestion.speaking_parser import SpeakingParser
from app.ingestion.test_splitter import TestSplitter

PARSERS = {
    "reading": ReadingParser(),
    "listening": ListeningParser(),
    "writing": WritingParser(),
    "speaking": SpeakingParser(),
}

CURATED_LISTENING_KEYS = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "curated"
    / "listening_answer_keys.json"
)

# Manual chart crops for Academic Writing Task 1 live here (see acceptance
# criteria). Only Academic Task 1 shows a chart/graph/map — General Training
# Task 1 is a letter with no stimulus image, so its crop is simply absent and
# the upload below is skipped, leaving that test with no image key.
CHARTS_DIR = Path(__file__).resolve().parent.parent / "data" / "charts"

# Writing stimulus images live in their own bucket, distinct from the Listening
# audio bucket. Overridable so the same script targets LocalStack in dev and
# real S3 in CI/prod.
WRITING_IMAGE_BUCKET = os.environ.get("WRITING_IMAGE_BUCKET", "goa-writing-files")

# Default to LocalStack's published port; AWS_ENDPOINT_URL overrides for real S3.
_S3_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or "http://localhost:4566"
_S3_REGION = os.environ.get("AWS_REGION", "us-east-1")

_s3_client = None


def _compute_text_hash(text: str) -> str:
    """SHA-256 of text content (first 16 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _find_answer_key_start(text: str) -> int | None:
    """Locate the real answer-key chapter, not an introductory reference to it."""
    matches = list(
        re.finditer(
            r"(?im)^\s*(?:Listening\s+and\s+Reading\s+)?Answer\s*keys?\s*$",
            text,
        )
    )
    return matches[-1].start() if matches else None


def _find_answer_key_section(text: str) -> str:
    """Extract the answer key section from the full book text.

    Parsers need the answer key appended to test blocks so they can
    extract correct answers.
    """
    start = _find_answer_key_start(text)
    return text[start:] if start is not None else ""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_curated_listening_key(slug: str, test_number: int) -> dict[str, Any] | None:
    """Return a visually verified official key when one is curated locally."""
    if not CURATED_LISTENING_KEYS.exists():
        return None
    payload = json.loads(CURATED_LISTENING_KEYS.read_text(encoding="utf-8"))
    key = payload.get(slug, {}).get(str(test_number))
    if key is None:
        return None
    answers = key.get("answers", {})
    if set(answers) != {str(number) for number in range(1, 41)}:
        raise ValueError(
            f"Curated Listening key for {slug}/test{test_number} must contain answers 1-40"
        )
    return key


def _get_s3_client():
    """Return one shared S3 client, built lazily on first use.

    boto3 clients are connectionless until a call is made, so a reading- or
    listening-only parse that never uploads a chart never touches the network.
    """
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=_S3_REGION,
            endpoint_url=_S3_ENDPOINT_URL,
        )
    return _s3_client


def _upload_writing_chart(slug: str, test_number: int, book_ref: str) -> str | None:
    """Upload the Task 1 chart crop for one writing test; return its S3 key.

    The crop is expected at ``data/charts/<slug>-test<N>-task1.png`` (e.g.
    ``data/charts/IELTS15-test1-task1.png``) — that is where manual crops land.
    If it is absent (every General Training test, and any Academic test not yet
    cropped) we return None so the parsed JSON keeps no image key, which is what
    makes re-running safe. When present it is uploaded under the deterministic
    key ``charts/<book_ref>-test-<N>-task1.png``; re-runs overwrite the same key,
    so the step stays idempotent.

    An upload failure is non-fatal: we warn and return None rather than discard
    a successfully parsed test over a transient S3 problem. A later re-run picks
    the chart back up.
    """
    chart_path = CHARTS_DIR / f"{slug}-test{test_number}-task1.png"
    if not chart_path.exists():
        return None

    image_key = f"charts/{book_ref}-test-{test_number}-task1.png"
    try:
        _get_s3_client().upload_file(
            str(chart_path),
            WRITING_IMAGE_BUCKET,
            image_key,
            ExtraArgs={"ContentType": "image/png"},
        )
    except Exception as exc:  # noqa: BLE001 - ingestion CLI: keep parsing going
        print(
            f"  [chart     ] Test {test_number}: [WARN] upload failed for "
            f"{chart_path.name}: {exc}"
        )
        return None

    print(
        f"  [chart     ] Test {test_number}: uploaded "
        f"s3://{WRITING_IMAGE_BUCKET}/{image_key}"
    )
    return image_key



def _write_metadata(
    book_dir: Path, slug: str, test_numbers: list[int], source_hash: str
) -> None:
    """Write a metadata.json summarizing what was parsed for this book."""
    meta = {
        "book_slug": slug,
        "tests": sorted(set(test_numbers)),
        "skills": SKILLS,
        "source_hash": source_hash,
    }
    _write_json(book_dir / "metadata.json", meta)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 2: Parse OCR text into normalized JSON.",
    )
    parser.add_argument(
        "--ocr-dir",
        type=Path,
        default=OCR_DIR,
        help="Directory containing OCR text files.",
    )
    parser.add_argument(
        "--parsed-dir",
        type=Path,
        default=PARSED_DIR,
        help="Output directory for parsed JSON.",
    )
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="Parse only this book slug (e.g. IELTS14).",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        choices=SKILLS,
        help="Parse only this skill area.",
    )
    parser.add_argument(
        "--test",
        type=int,
        default=None,
        help="Parse only this test number.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-parse even if source text has not changed.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write intermediate parser text to debug/ for manual inspection.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("STAGE 2: PARSE -> TXT -> JSON")
    print("=" * 70)
    print(f"  Source:  {args.ocr_dir}")
    print(f"  Output:  {args.parsed_dir}")
    if args.book:
        print(f"  Book:    {args.book}")
    if args.skill:
        print(f"  Skill:   {args.skill}")
    if args.test:
        print(f"  Test:    {args.test}")
    print()

    ocr_texts = discover_ocr_texts(args.ocr_dir, book=args.book)
    if not ocr_texts:
        print("[ERROR] No OCR text files found. Run ocr_books.py first.")
        return 1

    skills_to_parse = [args.skill] if args.skill else SKILLS
    results: list[dict] = []
    errors: list[str] = []

    for txt_path, slug in ocr_texts:
        print(f"--- {slug} ---")
        raw_text = txt_path.read_text(encoding="utf-8")
        source_hash = _compute_text_hash(raw_text)

        # Check if already parsed with same source
        sha_path = args.parsed_dir / slug / ".source_sha256"
        if not args.force and sha_path.exists():
            stored_hash = sha_path.read_text(encoding="utf-8").strip()
            if stored_hash == source_hash and not args.test and not args.skill:
                print(f"  [SKIP] Source unchanged (hash: {source_hash})")
                results.append({"slug": slug, "status": "skipped"})
                continue

        full_text = DEFAULT_NORMALIZER.normalize(raw_text)
        answer_key_start = _find_answer_key_start(full_text)
        question_text = (
            full_text[:answer_key_start] if answer_key_start is not None else full_text
        )
        splitter = TestSplitter()
        tests = splitter.split(question_text)
        answer_key_section = _find_answer_key_section(full_text)

        if not tests:
            print(f"  [WARN] No test blocks found in {txt_path.name}")
            continue

        test_numbers_to_parse = [args.test] if args.test else sorted(tests.keys())
        all_test_numbers: list[int] = []

        for test_num in test_numbers_to_parse:
            if test_num not in tests:
                print(f"  [WARN] Test {test_num} not found in {slug}")
                continue

            test_block = tests[test_num]

            for skill in skills_to_parse:
                skill_parser = PARSERS.get(skill)
                if not skill_parser:
                    continue

                # Append answer key section only for Reading and Listening
                parser_input = test_block
                if (
                    skill in ["reading", "listening"]
                    and answer_key_section
                    and answer_key_section not in test_block
                ):
                    parser_input = test_block + "\n" + answer_key_section

                if args.debug:
                    skill_parser.debug_dir = Path("debug") / slug / f"test{test_num}"

                label = f"{slug}/test{test_num}/{skill}"
                t0 = time.time()

                try:
                    skill_input = test_block if skill == "listening" else parser_input
                    parsed = skill_parser.parse_text(skill_input)
                    elapsed = time.time() - t0

                    # Ensure correct metadata
                    parsed["book_ref"] = f"IELTS-{slug.replace('IELTS', '')}"
                    parsed["test_number"] = test_num
                    if skill == "listening":
                        parsed["audio_s3_key"] = (
                            f"exam-audio/{parsed['book_ref']}/{test_num}/section1.mp3"
                        )
                        parsed["time_limit_seconds"] = 40 * 60
                        curated_key = _load_curated_listening_key(slug, test_num)
                        if curated_key is not None:
                            parsed["answer_key"] = curated_key
                    elif skill == "writing":
                        # Academic Task 1 asks the candidate to describe a chart;
                        # attach it here so the question is actually answerable.
                        image_key = _upload_writing_chart(
                            slug, test_num, parsed["book_ref"]
                        )
                        if image_key is not None:
                            parsed["image_s3_key"] = image_key

                    q_count = len(parsed.get("questions", []))
                    answer_key = parsed.get("answer_key", {})
                    ak_count = len(answer_key.get("answers", answer_key))

                    out_path = args.parsed_dir / slug / skill / f"test{test_num}.json"
                    _write_json(out_path, parsed)

                    print(
                        f"  [{skill:<10}] Test {test_num}: {q_count} questions, "
                        f"{ak_count} answers [{elapsed:.1f}s] → {out_path.name}"
                    )
                    results.append(
                        {"label": label, "status": "parsed", "questions": q_count}
                    )
                    all_test_numbers.append(test_num)

                except Exception as e:
                    elapsed = time.time() - t0
                    print(
                        f"  [{skill:<10}] Test {test_num}: [ERROR] {e} [{elapsed:.1f}s]"
                    )
                    errors.append(f"{label}: {e}")

        # Write metadata and source hash
        if all_test_numbers:
            _write_metadata(args.parsed_dir / slug, slug, all_test_numbers, source_hash)
            sha_path.parent.mkdir(parents=True, exist_ok=True)
            sha_path.write_text(source_hash + "\n", encoding="utf-8")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    parsed_count = sum(1 for r in results if r.get("status") == "parsed")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped")
    total_questions = sum(
        r.get("questions", 0) for r in results if r.get("status") == "parsed"
    )
    print(f"  Parsed:    {parsed_count} file(s)")
    print(f"  Skipped:   {skipped_count} book(s)")
    print(f"  Questions: {total_questions} total")
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

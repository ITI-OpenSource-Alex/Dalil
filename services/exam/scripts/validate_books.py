"""
Stage 4 — Validate
====================
Verifies parsed JSON files for structural correctness.

Checks per skill:

- **Reading**: 3 passages, 40 questions, 40 answer keys, no duplicates,
  metadata completeness.
- **Listening**: 4 sections, 40 questions, audio S3 key present.
- **Writing**: 2 tasks (Task 1 + Task 2), prompts > 20 chars.
- **Speaking**: Parts 1, 2, 3 present, Part 2 has bullet points.
- **All skills**: book_ref, test_number, exam_type, skill_area present.

Usage::

    python scripts/validate_books.py
    python scripts/validate_books.py --book IELTS14
    python scripts/validate_books.py --book IELTS14 --skill reading --test 1
    python scripts/validate_books.py --strict
"""

from __future__ import annotations

import argparse
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


def _validate_common(payload: dict, label: str) -> list[str]:
    """Validate fields common to all skills."""
    issues: list[str] = []
    for field in ("book_ref", "test_number", "exam_type", "skill_area"):
        if not payload.get(field):
            issues.append(f"{label}: missing '{field}'")
    return issues


def _validate_reading(payload: dict, label: str, *, strict: bool = False) -> list[str]:
    issues: list[str] = []
    questions = payload.get("questions", [])
    answer_key = payload.get("answer_key", {})
    passage_text = payload.get("passage_text")

    # Passages
    if passage_text:
        passages = passage_text.split("\n\n---\n\n")
        if len(passages) < 3:
            issues.append(f"{label}: expected 3 passages, got {len(passages)}")
    else:
        issues.append(f"{label}: no passage text")

    # Questions
    if len(questions) < 30:
        issues.append(f"{label}: expected ~40 questions, got {len(questions)}")
    if strict and len(questions) != 40:
        issues.append(
            f"{label}: strict: expected exactly 40 questions, got {len(questions)}"
        )

    # Answer keys
    if len(answer_key) < 30:
        issues.append(f"{label}: expected ~40 answer keys, got {len(answer_key)}")
    if strict and len(answer_key) != 40:
        issues.append(
            f"{label}: strict: expected exactly 40 answer keys, got {len(answer_key)}"
        )

    # Duplicate question numbers
    numbers = [q.get("number") for q in questions if q.get("number") is not None]
    if len(numbers) != len(set(numbers)):
        dupes = [n for n in numbers if numbers.count(n) > 1]
        issues.append(f"{label}: duplicate question numbers: {sorted(set(dupes))}")

    # Missing questions (gaps in 1-40)
    if strict:
        expected = set(range(1, 41))
        actual = set(numbers)
        missing = expected - actual
        if missing:
            issues.append(f"{label}: missing question numbers: {sorted(missing)}")

    return issues


def _validate_listening(
    payload: dict, label: str, *, strict: bool = False
) -> list[str]:
    issues: list[str] = []
    questions = payload.get("questions", [])
    answer_key = payload.get("answer_key", {})
    answers = (
        answer_key.get("answers", answer_key) if isinstance(answer_key, dict) else {}
    )
    audio_key = payload.get("audio_s3_key")

    if len(questions) < 30:
        issues.append(f"{label}: expected ~40 questions, got {len(questions)}")
    if strict and len(questions) != 40:
        issues.append(
            f"{label}: strict: expected exactly 40 questions, got {len(questions)}"
        )
    if len(answers) < 30:
        issues.append(f"{label}: expected ~40 answer keys, got {len(answers)}")
    if strict and len(answers) != 40:
        issues.append(
            f"{label}: strict: expected exactly 40 answer keys, got {len(answers)}"
        )

    if not audio_key:
        issues.append(f"{label}: no audio S3 key")

    # Verify all 4 sections present
    sections = set()
    for q in questions:
        s = q.get("section_number")
        if s:
            sections.add(s)
    if len(sections) < 4:
        issues.append(
            f"{label}: expected 4 sections, got {len(sections)} ({sorted(sections)})"
        )
    if strict:
        numbers = [q.get("number") for q in questions]
        expected_numbers = set(range(1, 41))
        if set(numbers) != expected_numbers:
            issues.append(
                f"{label}: missing question numbers: {sorted(expected_numbers - set(numbers))}"
            )

    return issues


def _validate_writing(payload: dict, label: str, *, strict: bool = False) -> list[str]:
    issues: list[str] = []
    questions = payload.get("questions", [])

    if len(questions) < 2:
        issues.append(
            f"{label}: expected 2 tasks (Task 1 + Task 2), got {len(questions)}"
        )
        return issues

    task1 = questions[0]
    task2 = questions[1]

    if "Writing Task 1" not in task1.get("question_type", ""):
        issues.append(f"{label}: Task 1 type mismatch: {task1.get('question_type')}")
    if "Writing Task 2" not in task2.get("question_type", ""):
        issues.append(f"{label}: Task 2 type mismatch: {task2.get('question_type')}")

    if len(task1.get("prompt", "")) < 20:
        issues.append(
            f"{label}: Task 1 prompt too short ({len(task1.get('prompt', ''))} chars)"
        )
    if len(task2.get("prompt", "")) < 20:
        issues.append(
            f"{label}: Task 2 prompt too short ({len(task2.get('prompt', ''))} chars)"
        )

    return issues


def _validate_speaking(payload: dict, label: str, *, strict: bool = False) -> list[str]:
    issues: list[str] = []
    questions = payload.get("questions", [])

    if not questions:
        issues.append(f"{label}: no questions extracted")
        return issues

    part1 = [q for q in questions if q.get("question_type") == "Speaking Part 1"]
    part2 = [q for q in questions if q.get("question_type") == "Speaking Part 2"]
    part3 = [q for q in questions if q.get("question_type") == "Speaking Part 3"]

    if not part1:
        issues.append(f"{label}: no Part 1 questions")
    if not part2:
        issues.append(f"{label}: no Part 2 cue card")
    else:
        bullets = part2[0].get("bullet_points", [])
        if not bullets:
            issues.append(f"{label}: Part 2 has no bullet points")
    if not part3:
        issues.append(f"{label}: no Part 3 discussion questions")

    return issues


VALIDATORS = {
    "reading": _validate_reading,
    "listening": _validate_listening,
    "writing": _validate_writing,
    "speaking": _validate_speaking,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 4: Validate parsed JSON files.",
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
        help="Validate only this book slug.",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        choices=SKILLS,
        help="Validate only this skill area.",
    )
    parser.add_argument(
        "--test",
        type=int,
        default=None,
        help="Validate only this test number.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce exact counts (40 questions, 40 answers, etc.).",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("STAGE 4: VALIDATE")
    print("=" * 70)
    print(f"  Source:  {args.parsed_dir}")
    if args.book:
        print(f"  Book:    {args.book}")
    if args.skill:
        print(f"  Skill:   {args.skill}")
    if args.test:
        print(f"  Test:    {args.test}")
    if args.strict:
        print("  Strict:  yes")
    print()

    json_files = discover_parsed_json(
        args.parsed_dir, book=args.book, skill=args.skill, test=args.test
    )

    if not json_files:
        print("[ERROR] No parsed JSON files found. Run parse_books.py first.")
        return 1

    all_issues: list[str] = []
    passed = 0
    failed = 0

    for json_path in json_files:
        parts = json_path.relative_to(args.parsed_dir).parts
        label = "/".join(parts)

        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as e:
            all_issues.append(f"{label}: invalid JSON: {e}")
            failed += 1
            continue

        # Common validation
        issues = _validate_common(payload, label)

        # Skill-specific validation
        skill = parts[1] if len(parts) >= 2 else payload.get("skill_area", "")
        validator = VALIDATORS.get(skill)
        if validator:
            issues.extend(validator(payload, label, strict=args.strict))

        if issues:
            failed += 1
            for issue in issues:
                print(f"  [FAIL] {issue}")
            all_issues.extend(issues)
        else:
            passed += 1
            q_count = len(payload.get("questions", []))
            print(f"  [PASS] {label}: {q_count} questions")

    # Report
    print()
    print("=" * 70)
    print("REPORT")
    print("=" * 70)
    print(f"  Files checked: {len(json_files)}")
    print(f"  Passed:        {passed}")
    print(f"  Failed:        {failed}")
    print(f"  Issues:        {len(all_issues)}")

    if all_issues:
        print()
        print("ALL ISSUES:")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1

    print()
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

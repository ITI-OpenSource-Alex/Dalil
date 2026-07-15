"""
Pipeline Orchestrator
======================
Single entry point for the stage-based ingestion pipeline.

Delegates to the individual stage scripts.  Each stage remains independently
runnable.

Usage::

    python scripts/pipeline.py --stage ocr
    python scripts/pipeline.py --stage parse
    python scripts/pipeline.py --stage ingest
    python scripts/pipeline.py --stage validate
    python scripts/pipeline.py --all
    python scripts/pipeline.py --all --book IELTS14
    python scripts/pipeline.py --stage parse --book IELTS14 --skill reading --test 1
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)

STAGES = {
    "ocr": "ocr_books.py",
    "parse": "parse_books.py",
    "ingest": "ingest_books.py",
    "validate": "validate_books.py",
}

ALL_STAGES_ORDER = ["ocr", "parse", "ingest", "validate"]


def _build_command(stage: str, args: argparse.Namespace) -> list[str]:
    """Build the command-line arguments for a stage script."""
    script = os.path.join(SCRIPTS_DIR, STAGES[stage])
    cmd = [sys.executable, script]

    if args.book:
        cmd.extend(["--book", args.book])
    if args.force:
        cmd.append("--force")

    # Stage-specific arguments
    if stage in ("parse", "validate") and args.skill:
        cmd.extend(["--skill", args.skill])
    if stage in ("parse", "ingest", "validate") and args.test:
        cmd.extend(["--test", str(args.test)])
    if stage == "ingest" and args.dry_run:
        cmd.append("--dry-run")
    if stage == "validate" and args.strict:
        cmd.append("--strict")

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cambridge IELTS ingestion pipeline orchestrator.",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--stage",
        choices=list(STAGES.keys()),
        help="Run a single stage.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run all stages in order: ocr → parse → ingest → validate.",
    )

    parser.add_argument("--book", type=str, default=None, help="Filter by book slug.")
    parser.add_argument("--skill", type=str, default=None, help="Filter by skill area.")
    parser.add_argument("--test", type=int, default=None, help="Filter by test number.")
    parser.add_argument("--force", action="store_true", help="Force re-processing.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (ingest stage only).")
    parser.add_argument("--strict", action="store_true", help="Strict validation.")

    args = parser.parse_args()

    stages = ALL_STAGES_ORDER if args.all else [args.stage]

    print("=" * 70)
    print("CAMBRIDGE IELTS INGESTION PIPELINE")
    print("=" * 70)
    print(f"  Stages: {' → '.join(stages)}")
    if args.book:
        print(f"  Book:   {args.book}")
    if args.skill:
        print(f"  Skill:  {args.skill}")
    if args.test:
        print(f"  Test:   {args.test}")
    print()

    for stage in stages:
        cmd = _build_command(stage, args)
        print(f">>> Running: {' '.join(cmd)}")
        print()

        result = subprocess.run(cmd, cwd=PROJECT_ROOT)

        if result.returncode != 0:
            print()
            print(f"[ABORT] Stage '{stage}' failed with exit code {result.returncode}.")
            print(f"        Fix the issue and re-run: python scripts/pipeline.py --stage {stage}")
            return result.returncode

        print()

    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

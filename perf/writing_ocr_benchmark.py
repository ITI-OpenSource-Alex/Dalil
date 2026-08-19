"""Benchmark the Writing engine on examiner-banded answers from book OCR.

The source answers already live in ``services/exam/data/ocr``.  This harness
references exact line spans rather than copying third-party prose into another
tracked fixture.  Reports contain hashes and scores, never the essay text.

Only Task 2 is included.  Academic Task 1 cannot be evaluated fairly without
the source chart, and a text-only run would confound chart understanding with
Writing quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WRITING_URL = "http://localhost:8000"


@dataclass(frozen=True)
class SampleSpec:
    sample_id: str
    book: str
    test_number: int
    answer_start_line: int
    answer_end_line: int
    published_band: float
    task_prompt: str

    @property
    def source_path(self) -> Path:
        return REPO_ROOT / "services" / "exam" / "data" / "ocr" / self.book / "full.txt"


SAMPLES = (
    SampleSpec(
        "ielts15-test1-task2",
        "IELTS15",
        1,
        3452,
        3472,
        7.0,
        (
            "In some countries, owning a home rather than renting one is very "
            "important for people. Why might this be the case? Do you think this "
            "is a positive or negative situation?"
        ),
    ),
    SampleSpec(
        "ielts16-test1-task2",
        "IELTS16",
        1,
        3493,
        3511,
        6.0,
        (
            "In some countries, more and more people are becoming interested in "
            "finding out about the history of the house or building they live in. "
            "What are the reasons for this? How can people research this?"
        ),
    ),
    SampleSpec(
        "ielts16-test2-task2",
        "IELTS16",
        2,
        3552,
        3563,
        4.5,
        (
            "In their advertising, businesses nowadays usually emphasise that "
            "their products are new in some way. Why is this? Do you think it is "
            "a positive or negative development?"
        ),
    ),
    SampleSpec(
        "ielts16-test3-task2",
        "IELTS16",
        3,
        3608,
        3630,
        7.0,
        (
            "Many manufactured food and drink products contain high levels of "
            "sugar, which causes many health problems. Sugary products should be "
            "made more expensive to encourage people to consume less sugar. Do "
            "you agree or disagree?"
        ),
    ),
    SampleSpec(
        "ielts16-test4-task2",
        "IELTS16",
        4,
        3683,
        3698,
        4.0,
        (
            "In the future all cars, buses and trucks will be driverless. The only "
            "people travelling inside these vehicles will be passengers. Do you "
            "think the advantages of driverless vehicles outweigh the disadvantages?"
        ),
    ),
    SampleSpec(
        "ielts17-test1-task2",
        "IELTS17",
        1,
        3464,
        3478,
        6.5,
        (
            "It is important for people to take risks, both in their professional "
            "lives and their personal lives. Do you think the advantages of taking "
            "risks outweigh the disadvantages?"
        ),
    ),
)


@dataclass(frozen=True)
class ExtractedSample:
    spec: SampleSpec
    essay: str
    source_sha256: str
    essay_sha256: str
    word_count: int
    ocr_artifacts: dict[str, int]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _ocr_artifacts(text: str) -> dict[str, int]:
    return {
        "literal_backslash_n": text.count("\\n"),
        "standalone_pipe": len(re.findall(r"(?<!\w)\|(?!\w)", text)),
        "digit_touching_letter": len(
            re.findall(r"(?:[A-Za-z]\d|\d[A-Za-z])", text)
        ),
    }


def extract_sample(spec: SampleSpec) -> ExtractedSample:
    source_bytes = spec.source_path.read_bytes()
    lines = source_bytes.decode("utf-8-sig").splitlines()
    header_index = spec.answer_start_line - 2
    band_index = spec.answer_start_line - 1
    if "WRITING TASK 2" not in lines[header_index - 1]:
        raise ValueError(
            f"{spec.sample_id}: line anchor moved; expected Task 2 header at "
            f"{header_index}"
        )
    band_match = re.search(r"Band\s+(\d(?:\.\d)?)\s+score", lines[band_index - 1])
    if not band_match:
        raise ValueError(f"{spec.sample_id}: examiner-band line is missing")
    anchored_band = float(band_match.group(1))
    if anchored_band != spec.published_band:
        raise ValueError(
            f"{spec.sample_id}: anchored band {anchored_band} != configured "
            f"{spec.published_band}"
        )

    answer_lines = lines[spec.answer_start_line - 1 : spec.answer_end_line]
    essay = " ".join(line.strip() for line in answer_lines if line.strip())
    forbidden = ("examiner's comment", "examiner’s comment", "This response")
    if any(marker.lower() in essay.lower() for marker in forbidden):
        raise ValueError(f"{spec.sample_id}: examiner commentary leaked into answer")

    return ExtractedSample(
        spec=spec,
        essay=essay,
        source_sha256=_sha256(source_bytes),
        essay_sha256=_sha256(essay.encode("utf-8")),
        word_count=_word_count(essay),
        ocr_artifacts=_ocr_artifacts(essay),
    )


def nearest_rank_percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return round(ordered[index], 3)


def score_sample(
    sample: ExtractedSample,
    *,
    writing_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    nonce = uuid.uuid4().hex
    started = time.perf_counter()
    response = httpx.post(
        f"{writing_url.rstrip('/')}/essays/evaluate/exam",
        json={
            "userId": f"ocr-writing-bench-{nonce}",
            "essayText": sample.essay,
            "examType": "academic",
            "examSessionId": f"ocr-writing-bench-{nonce}",
            "taskNumber": 2,
            "taskPrompt": sample.spec.task_prompt,
            "inputSource": "ocr",
        },
        timeout=timeout_seconds,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.is_error:
        raise RuntimeError(
            f"Writing service returned {response.status_code}: {response.text[:1000]}"
        )
    payload = response.json()
    predicted_band = float(payload["overall_band"])
    delta = predicted_band - sample.spec.published_band
    criteria = {
        row["criterion"]: float(row["band_score"])
        for row in payload.get("evaluations", [])
    }
    return {
        "sample_id": sample.spec.sample_id,
        "book": sample.spec.book,
        "test_number": sample.spec.test_number,
        "published_band": sample.spec.published_band,
        "predicted_band": predicted_band,
        "delta": round(delta, 3),
        "absolute_error": round(abs(delta), 3),
        "exact": delta == 0,
        "within_half_band": abs(delta) <= 0.5,
        "within_one_band": abs(delta) <= 1.0,
        "criteria": criteria,
        "latency_ms": round(elapsed_ms, 3),
        "from_cache": bool(payload.get("from_cache")),
        "word_count": sample.word_count,
        "source_sha256": sample.source_sha256,
        "essay_sha256": sample.essay_sha256,
        "ocr_artifacts": sample.ocr_artifacts,
    }


def aggregate(rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["delta"]) for row in rows]
    absolute = [float(row["absolute_error"]) for row in rows]
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "n_total": len(rows) + len(failures),
        "n_scored": len(rows),
        "n_failed": len(failures),
        "exact_agreement": round(sum(row["exact"] for row in rows) / len(rows), 4)
        if rows
        else None,
        "within_half_band": round(
            sum(row["within_half_band"] for row in rows) / len(rows), 4
        )
        if rows
        else None,
        "within_one_band": round(
            sum(row["within_one_band"] for row in rows) / len(rows), 4
        )
        if rows
        else None,
        "mae": round(statistics.mean(absolute), 4) if absolute else None,
        "rmse": round(math.sqrt(statistics.mean([value**2 for value in deltas])), 4)
        if deltas
        else None,
        "mean_signed_error": round(statistics.mean(deltas), 4) if deltas else None,
        "latency_ms": {
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "p95": nearest_rank_percentile(latencies, 0.95),
            "max": round(max(latencies), 3) if latencies else None,
        },
    }


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run(args: argparse.Namespace) -> tuple[dict[str, Any], Path | None]:
    samples = [extract_sample(spec) for spec in SAMPLES]
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    if not args.dry_run:
        for index, sample in enumerate(samples, start=1):
            print(
                f"[{index}/{len(samples)}] scoring {sample.spec.sample_id} "
                f"(published {sample.spec.published_band})",
                flush=True,
            )
            try:
                row = score_sample(
                    sample,
                    writing_url=args.writing_url,
                    timeout_seconds=args.timeout,
                )
                rows.append(row)
                print(
                    f"  predicted={row['predicted_band']:.1f} "
                    f"delta={row['delta']:+.1f} latency={row['latency_ms']:.0f}ms",
                    flush=True,
                )
            except Exception as exc:  # Preserve partial evidence in the report.
                failure = {
                    "sample_id": sample.spec.sample_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                failures.append(failure)
                print(f"  FAILED: {failure['error']}", flush=True)

    report = {
        "benchmark": "writing-ocr-examiner-band/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "dry_run": args.dry_run,
        "valid": args.dry_run or (len(rows) == len(samples) and not failures),
        "scope": {
            "task": "IELTS Academic Writing Task 2",
            "books": sorted({sample.spec.book for sample in samples}),
            "labels": "published candidate bands and examiner comments in book OCR",
            "input_source": "ocr",
            "normalization": (
                "deterministic Writing-service OCR cleanup; typed submissions are "
                "not normalized"
            ),
            "excluded": (
                "Task 1 responses: source chart/image is required for a fair Task "
                "Achievement score"
            ),
            "interpretation": (
                "end-to-end OCR-normalization-to-scoring benchmark; only the "
                "service's deterministic artifact rules are applied"
            ),
        },
        "model": args.model,
        "writing_url": args.writing_url,
        "metrics": aggregate(rows, failures),
        "samples": rows,
        "failures": failures,
        "dataset_manifest": [
            {
                **asdict(sample.spec),
                "source_path": str(sample.spec.source_path.relative_to(REPO_ROOT)),
                "source_sha256": sample.source_sha256,
                "essay_sha256": sample.essay_sha256,
                "word_count": sample.word_count,
                "ocr_artifacts": sample.ocr_artifacts,
            }
            for sample in samples
        ],
    }

    output_path: Path | None = None
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"wrote {output_path}", flush=True)
    return report, output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writing-url", default=DEFAULT_WRITING_URL)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--model", default="configured WRITING_MODEL")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and fingerprint OCR samples without calling the Writing engine",
    )
    return parser.parse_args()


def main() -> int:
    report, _ = run(parse_args())
    print(json.dumps(report["metrics"], indent=2), flush=True)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

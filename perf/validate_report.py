"""GOA-036 — validate a k6 summary against the expected report schema.

The acceptance criterion is "Load test report JSON validates against expected
schema and is uploaded to S3". This is the validating half; run-load-test.sh
does the upload.

The point is not JSON well-formedness -- k6 always emits valid JSON. It is that
every metric the report and the bottleneck analysis actually read is PRESENT. A
scenario that silently stopped running omits its metric entirely, and without
this check the report would render a blank cell rather than fail.

    python perf/validate_report.py perf/reports/20260811T032552Z-k6.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = Path(__file__).parent / "schemas" / "k6-report.schema.json"


def validate(report_path: Path, schema_path: Path) -> list[str]:
    """Returns a list of problems; empty means valid."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    if jsonschema is not None:
        validator = jsonschema.Draft7Validator(schema)
        for error in sorted(validator.iter_errors(report), key=lambda e: list(e.path)):
            location = "/".join(str(p) for p in error.path) or "(root)"
            problems.append(f"{location}: {error.message}")
        return problems

    # Fallback so this check is never skipped just because a dependency is
    # missing. It covers the assertion that actually matters -- required
    # metrics present, trends carrying percentiles -- rather than the whole
    # schema.
    problems.append(
        "NOTE: jsonschema not installed; ran the built-in required-key check only "
        "(pip install jsonschema for full validation)"
    )
    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        problems.append("(root): 'metrics' missing or not an object")
        return problems

    for name in schema["properties"]["metrics"]["required"]:
        if name not in metrics:
            problems.append(
                f"metrics/{name}: required metric is absent -- the scenario that "
                f"emits it did not run"
            )
            continue
        spec = schema["properties"]["metrics"]["properties"].get(name, {})
        ref = spec.get("$ref", "").rsplit("/", 1)[-1]
        for key in schema.get("definitions", {}).get(ref, {}).get("required", []):
            if key not in metrics[name]:
                problems.append(f"metrics/{name}: missing '{key}'")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--schema", type=Path, default=SCHEMA)
    args = parser.parse_args()

    problems = validate(args.report, args.schema)
    hard = [p for p in problems if not p.startswith("NOTE:")]

    for problem in problems:
        print(("  " if problem.startswith("NOTE:") else "  FAIL ") + problem)

    if hard:
        print(f"\n{args.report.name}: INVALID ({len(hard)} problem(s))")
        sys.exit(1)
    print(f"\n{args.report.name}: valid")


if __name__ == "__main__":
    main()

"""Tri-language conformance driver for the speaking evaluation contract.

SPEAK-EVAL-003 acceptance: shared fixtures decode in all three languages.

Runs the Go, Python and TypeScript digest emitters over every fixture and
compares their output line by line. See README.md for the digest format and for
why invalid fixtures are tiered.

    python packages/contracts/conformance/run_conformance.py

Exit code 0 means the three implementations agree on every fixture.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE.parent
REPO = CONTRACTS.parent.parent
FIXTURES = CONTRACTS / "fixtures" / "speaking-evaluation"
SPEAKING = REPO / "services" / "speaking"
TS_DIR = CONTRACTS / "ts"

# Defects that need the frozen rubric to detect. The rubric lives with the Go
# scorer that must cite it; shipping a second copy to the consumers is how a
# rubric forks. See README.md.
TIER_2_INVALID = {"invented-descriptor-id.json"}


class Emitter:
    """One language's digest producer."""

    def __init__(self, name: str, argv_for: object, cwd: Path) -> None:
        self.name = name
        self._argv_for = argv_for
        self.cwd = cwd

    def run(self, fixture: Path) -> tuple[list[str], str]:
        proc = subprocess.run(
            self._argv_for(fixture),  # type: ignore[operator]
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"{self.name} emitter failed on {fixture.name} "
                f"(exit {proc.returncode})\n{proc.stdout}\n{proc.stderr}"
            )
        # splitlines() rather than a byte compare: three runtimes on Windows
        # disagree about CRLF, and a line ending is not a contract violation.
        return proc.stdout.splitlines(), proc.stderr.strip()


def build_go(workdir: Path) -> Path:
    """Compile the Go emitter once instead of `go run` per fixture."""
    binary = workdir / ("contract-digest.exe" if os.name == "nt" else "contract-digest")
    subprocess.run(
        ["go", "build", "-o", str(binary), "./cmd/contract-digest"],
        cwd=SPEAKING,
        check=True,
    )
    return binary


def build_typescript(workdir: Path) -> Path:
    """Compile the TypeScript emitter and the contract module it imports.

    Compiled to CommonJS so plain node can run the result without a package
    type declaration or a loader flag. The source is authored as ES modules; the
    contract module is what services import, and it should not be reshaped to
    suit a test harness.
    """
    out = workdir / "ts"
    tsc = TS_DIR / "node_modules" / ".bin" / ("tsc.cmd" if os.name == "nt" else "tsc")
    if not tsc.exists():
        raise RuntimeError(
            f"typescript is not installed at {tsc}. "
            f"Run `npm install` in {TS_DIR}."
        )
    subprocess.run(
        [
            str(tsc),
            str(HERE / "emit_typescript.ts"),
            "--outDir", str(out),
            "--rootDir", str(CONTRACTS),
            "--module", "commonjs",
            "--moduleResolution", "node10",
            "--target", "es2020",
            "--strict",
            "--skipLibCheck",
            "--ignoreDeprecations", "6.0",
        ],
        check=True,
    )
    return out / "conformance" / "emit_typescript.js"


def report(fixture: Path, results: dict[str, list[str]]) -> bool:
    """Compare every emitter against Go. Returns True if they agree."""
    reference_name = "go"
    reference = results[reference_name]
    agreed = True

    for name, lines in results.items():
        if name == reference_name or lines == reference:
            continue
        agreed = False
        print(f"\n  MISMATCH {reference_name} vs {name} on {fixture.name}")
        diff = difflib.unified_diff(
            reference, lines, fromfile=reference_name, tofile=name, lineterm=""
        )
        for line in diff:
            print(f"    {line}")

    return agreed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="keep the compiled emitters for debugging",
    )
    args = parser.parse_args()

    for tool in ("go", "node"):
        if shutil.which(tool) is None:
            print(f"error: {tool} is not on PATH", file=sys.stderr)
            return 2

    workdir = Path(tempfile.mkdtemp(prefix="goa-conformance-"))
    try:
        print("building emitters...")
        go_binary = build_go(workdir)
        ts_entry = build_typescript(workdir)

        emitters = [
            Emitter("go", lambda f: [str(go_binary), str(f)], SPEAKING),
            Emitter(
                "python",
                lambda f: [sys.executable, str(HERE / "emit_python.py"), str(f)],
                REPO,
            ),
            Emitter("typescript", lambda f: ["node", str(ts_entry), str(f)], REPO),
        ]

        valid = sorted(FIXTURES.glob("valid-*.json"))
        invalid = sorted((FIXTURES / "invalid").glob("*.json"))
        if not valid or not invalid:
            print(f"error: no fixtures found under {FIXTURES}", file=sys.stderr)
            return 2

        failures = 0

        print(f"\nvalid fixtures ({len(valid)}) - all three must agree line for line")
        for fixture in valid:
            results = {e.name: e.run(fixture)[0] for e in emitters}
            for name, lines in results.items():
                if not lines or lines[0] != "verdict=accepted":
                    print(f"\n  {fixture.name}: {name} REJECTED a valid fixture")
                    failures += 1
            if report(fixture, results):
                print(f"  ok  {fixture.name}  ({len(results['go'])} digest lines)")
            else:
                failures += 1

        print(f"\ninvalid fixtures ({len(invalid)}) - must be rejected")
        for fixture in invalid:
            tier2 = fixture.name in TIER_2_INVALID
            expected = {"go"} if tier2 else {"go", "python", "typescript"}
            rejected = set()
            for e in emitters:
                lines, _ = e.run(fixture)
                if lines and lines[0] == "verdict=rejected":
                    rejected.add(e.name)

            missing = expected - rejected
            if missing:
                print(
                    f"\n  {fixture.name}: accepted by {', '.join(sorted(missing))} "
                    f"but must be rejected"
                )
                failures += 1
            else:
                tier = "tier 2, go only" if tier2 else "tier 1, all three"
                print(f"  ok  {fixture.name}  (rejected by {tier})")

        print()
        if failures:
            print(f"FAILED: {failures} problem(s)")
            return 1
        print(
            f"PASSED: {len(valid)} valid and {len(invalid)} invalid fixtures, "
            f"three implementations in agreement"
        )
        return 0
    finally:
        if args.keep_build:
            print(f"build kept at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

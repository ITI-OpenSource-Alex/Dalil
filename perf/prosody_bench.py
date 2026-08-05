"""GOA-133 — does the pipeline let Fluency and Pronunciation see delivery at all?

One harness, run twice (--phase pre, --phase post). Two levels of evidence:

LEVEL A -- mechanism. Free, exact, unaffected by the fixtures being synthetic.
    Does /stt return anything beyond the transcript? Do two recordings of the
    same words with radically different delivery produce identical STT output?
    If yes, the acoustic information is destroyed before any agent sees it, and
    no band difference is possible regardless of prompt wording.

LEVEL B -- bands. Costs LLM calls and is only directional on synthetic audio.
    Feed both arms of each pair to the real agents and compare the bands.

Level A is the claim; Level B is the confirmation. Reporting only Level B would
be weaker: a null result there could be explained away as "the model didn't
notice", whereas Level A shows there was nothing to notice.

Usage:
    docker compose up -d speech speaking postgres
    python perf/prosody_bench.py --phase pre --repeats 3
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "perf" / "fixtures" / "prosody"
SPEECH_URL = os.environ.get("SPEECH_URL", "http://localhost:8086")
SPEAKING_URL = os.environ.get("SPEAKING_URL", "http://localhost:8082")
INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "supersecret_internal_key_123")

CRITERIA = (
    "Fluency and Coherence",
    "Lexical Resource",
    "Grammatical Range and Accuracy",
    "Pronunciation",
)


def transcribe(path: Path) -> dict:
    with path.open("rb") as fh:
        response = httpx.post(
            f"{SPEECH_URL}/stt",
            files={"audio": (path.name, fh, "audio/wav")},
            timeout=900.0,
        )
    response.raise_for_status()
    return response.json()


def evaluate(transcript: str, stt: dict | None = None) -> dict:
    """Drive the real four-agent swarm via the holistic endpoint.

    The holistic REST path rather than the WebSocket: what is under test here is
    what reaches the AGENTS, and the transport does not change that. Using it
    keeps the harness runnable without a Gateway, a session and an audio stream.

    A session where every agent fails returns 500 -- correct behaviour since
    GOA-134, and not a reason to abandon the run. It is recorded as a session
    that produced no scores and folded into criterion_completion_rate, because a
    harness that dies on the first degraded session measures nothing at all.
    """
    try:
        response = httpx.post(
            f"{SPEAKING_URL}/internal/evaluate/holistic",
            headers={"x-Internal-Api-Key": INTERNAL_KEY},
            json={
                "concatenated_transcript": transcript,
                "user_id": "prosody-bench",
                # Forwarded post-GOA-133. Absent pre-fix, and absent from an old
                # sidecar's response, in which case the handler omits the feature
                # block rather than rendering zeros.
                "duration_s": (stt or {}).get("duration_s", 0.0),
                "words": (stt or {}).get("words", []),
            },
            timeout=300.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "status": "failed",
            "dimensions": {},
            "session_error": f"HTTP {exc.response.status_code}",
        }
    except httpx.HTTPError as exc:
        return {
            "status": "failed",
            "dimensions": {},
            "session_error": f"{type(exc).__name__}: {exc}",
        }


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation, computed here to avoid a scipy dependency in perf/."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (
        sum((a - mx) ** 2 for a in rx) ** 0.5
        * sum((b - my) ** 2 for b in ry) ** 0.5
    )
    return round(num / den, 4) if den else None


def level_a(manifest: list[dict]) -> dict:
    """Mechanism: what does the pipeline actually carry?"""
    per_pair = []
    stt_keys: set[str] = set()

    for entry in manifest:
        fluent = transcribe(FIXTURE_DIR / entry["fluent"])
        halting = transcribe(FIXTURE_DIR / entry["halting"])
        stt_keys |= set(fluent) | set(halting)

        per_pair.append({
            "pair": entry["pair"],
            "transcripts_identical": fluent["transcript"].strip() == halting["transcript"].strip(),
            "fluent_duration_s": entry["fluent_duration_s"],
            "halting_duration_s": entry["halting_duration_s"],
            "duration_ratio": round(
                entry["halting_duration_s"] / entry["fluent_duration_s"], 2
            ),
            "stt_reports_duration": "duration_s" in fluent,
            "stt_reports_words": bool(fluent.get("words")),
            "stt_reports_segments": bool(fluent.get("segments")),
        })

    identical = sum(1 for p in per_pair if p["transcripts_identical"])
    return {
        "stt_response_keys": sorted(stt_keys),
        "carries_timing": any(k in stt_keys for k in ("words", "segments", "duration_s")),
        "pairs_with_identical_transcripts": f"{identical}/{len(per_pair)}",
        "per_pair": per_pair,
    }


def level_b(manifest: list[dict], repeats: int, controlled: bool = True) -> dict:
    """Bands: does a large delivery difference move anything?

    `controlled` (the default) sends the FLUENT arm's transcript text for both
    arms, so the only thing that differs between them is the audio each arm's
    features were derived from. Whisper renders the stretched audio with slightly
    different punctuation and casing ("deal," vs "deal.", "17" vs "seventeen"),
    which is a text difference, and a text difference is exactly what this
    experiment must not contain: with it, a band delta could be attributed to
    wording rather than delivery.

    Set controlled=False to use each arm's own transcript -- more realistic, and
    what a real session would send, but confounded.
    """
    raw: list[dict] = []

    for entry in manifest:
        reference_stt = transcribe(FIXTURE_DIR / entry["fluent"])
        for arm in ("fluent", "halting"):
            path = FIXTURE_DIR / entry[arm]
            stt = transcribe(path)
            if controlled:
                # Own audio for features, shared text for the prompt.
                stt = {**stt, "transcript": reference_stt["transcript"]}
            for run in range(repeats):
                started = time.perf_counter()
                result = evaluate(stt["transcript"], stt)
                elapsed_ms = (time.perf_counter() - started) * 1000
                # Exclude criteria that produced no score. A timed-out agent
                # carries band 0.0 in the payload, and counting that as a real
                # band is exactly the BUG-055 shape this project keeps finding --
                # the first version of this harness fell for it and reported
                # deltas of ~4 bands on byte-identical input.
                bands = {
                    name: detail.get("band")
                    for name, detail in (result.get("dimensions") or {}).items()
                    if not detail.get("timed_out")
                }
                incomplete = [
                    name
                    for name, detail in (result.get("dimensions") or {}).items()
                    if detail.get("timed_out")
                ]
                raw.append({
                    "pair": entry["pair"],
                    "arm": arm,
                    "run": run,
                    "duration_s": entry[f"{arm}_duration_s"],
                    "word_count": len(stt["transcript"].split()),
                    "wpm": round(
                        len(stt["transcript"].split())
                        / (entry[f"{arm}_duration_s"] / 60.0),
                        1,
                    ),
                    "bands": bands,
                    "unscored_criteria": incomplete,
                    "session_error": result.get("session_error"),
                    "overall_band": result.get("overall_band"),
                    "completed_count": result.get("completed_count"),
                    "elapsed_ms": round(elapsed_ms, 1),
                })

    def median_band(pair: str, arm: str, criterion: str) -> float | None:
        values = [
            r["bands"].get(criterion)
            for r in raw
            if r["pair"] == pair and r["arm"] == arm and r["bands"].get(criterion) is not None
        ]
        return statistics.median(values) if values else None

    total_slots = len(raw) * len(CRITERIA)
    scored_slots = sum(len(r["bands"]) for r in raw)
    metrics: dict = {
        "sessions": len(raw),
        # The validity gate for everything below. A criterion that timed out in
        # one arm and completed in the other cannot be compared at all, so a low
        # rate here means the deltas rest on very few usable pairs.
        "criterion_completion_rate": round(scored_slots / total_slots, 3) if total_slots else None,
        "per_criterion": {},
        "raw": raw,
    }

    for criterion in CRITERIA:
        deltas, agreements, spreads = [], [], []
        for entry in manifest:
            fluent = median_band(entry["pair"], "fluent", criterion)
            halting = median_band(entry["pair"], "halting", criterion)
            if fluent is None or halting is None:
                continue
            deltas.append(abs(fluent - halting))
            agreements.append(fluent > halting)

        # Repeat spread is the NOISE FLOOR. A cross-arm delta of ~0 only means
        # "inert" if the same file scored the same across repeats; if the spread
        # is wide, the honest finding is "dominated by sampling noise", which is a
        # different defect and equally reportable.
        for entry in manifest:
            for arm in ("fluent", "halting"):
                values = [
                    r["bands"].get(criterion)
                    for r in raw
                    if r["pair"] == entry["pair"]
                    and r["arm"] == arm
                    and r["bands"].get(criterion) is not None
                ]
                if len(values) > 1:
                    spreads.append(max(values) - min(values))

        wpms = [r["wpm"] for r in raw if r["bands"].get(criterion) is not None]
        bands = [r["bands"][criterion] for r in raw if r["bands"].get(criterion) is not None]

        metrics["per_criterion"][criterion] = {
            "mean_abs_delta": round(statistics.fmean(deltas), 3) if deltas else None,
            "directional_agreement": (
                f"{sum(agreements)}/{len(agreements)}" if agreements else None
            ),
            "median_repeat_spread": round(statistics.median(spreads), 3) if spreads else None,
            "spearman_wpm_vs_band": spearman(wpms, bands) if len(wpms) >= 3 else None,
            "n_pairs": len(deltas),
        }

    return metrics


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pre", "post"], required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", default=str(REPO_ROOT / "perf" / "reports"))
    parser.add_argument(
        "--level-a-only",
        action="store_true",
        help="mechanism check only; skips every LLM call",
    )
    parser.add_argument(
        "--uncontrolled",
        action="store_true",
        help="send each arm's own transcript instead of a shared one (confounded)",
    )
    args = parser.parse_args()

    manifest_path = FIXTURE_DIR / "manifest.json"
    if not manifest_path.exists():
        print(f"missing {manifest_path}; run perf/make_prosody_fixtures.py", file=sys.stderr)
        return 1
    manifest = [e for e in json.loads(manifest_path.read_text(encoding="utf-8")) if e["valid"]]

    a = level_a(manifest)
    b = None if args.level_a_only else level_b(
        manifest, args.repeats, controlled=not args.uncontrolled
    )

    report = {
        "ticket": "GOA-133",
        "phase": args.phase,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "providers": {
            "stt": {"impl": "faster-whisper", "model": "small", "device": "cpu", "real": True},
            "llm": {
                "base_url": os.environ.get("ANTHROPIC_BASE_URL", "<unset>"),
                "model": os.environ.get("LLM_MODEL", "claude-opus-4-8"),
                "real": b is not None,
            },
        },
        # Loud, structured, and impossible to miss when reading the artefact.
        "fixtures": {
            "synthetic": True,
            "source": "Piper TTS via the speech sidecar, not human speech",
            "limitation": (
                "Absolute band values are meaningless: Piper's prosody is uniform, so "
                "the fluent arm is more fluent than any real candidate, and Whisper "
                "transcribes clean TTS with optimistic confidence. There are no "
                "disfluencies, accent or self-correction -- the phenomena Pronunciation "
                "is meant to assess. Use for MECHANISM (does the pipeline carry timing) "
                "and DIRECTION (does delivery move the band at all), never for calibration."
            ),
            "n_pairs": len(manifest),
            "repeats": args.repeats,
            "controlled_text": not args.uncontrolled,
        },
        "metrics": {"level_a_mechanism": a, "level_b_bands": b},
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"GOA-133-{args.phase}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {path}\n")

    print("LEVEL A -- mechanism")
    print(f"  /stt response keys      : {a['stt_response_keys']}")
    print(f"  carries any timing      : {a['carries_timing']}")
    print(f"  identical transcripts   : {a['pairs_with_identical_transcripts']} pairs")
    for p in a["per_pair"]:
        print(
            f"    {p['pair']}: {p['fluent_duration_s']}s vs {p['halting_duration_s']}s "
            f"({p['duration_ratio']}x)  identical_text={p['transcripts_identical']}"
        )

    if b:
        print("\nLEVEL B -- bands (synthetic fixtures; direction only)")
        for criterion, m in b["per_criterion"].items():
            print(
                f"  {criterion:<32} delta={m['mean_abs_delta']}  "
                f"agree={m['directional_agreement']}  "
                f"noise={m['median_repeat_spread']}  rho={m['spearman_wpm_vs_band']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

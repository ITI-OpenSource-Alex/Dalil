"""Run candidate clips through the speech sidecar to obtain measured prosody.

SPEAK-EVAL-007, the goa_audio lane. Audio -> speech sidecar -> prosody -> swarm,
which is the path the product actually runs, minus the WebSocket transport.

The one thing this file has to get right is stitching. Each answer is a separate
clip, and prosody is computed from word timings, so the naive concatenation --
offset each clip's words by the wall-clock position of its source audio --
reintroduces exactly the defect SPEAK-EVAL-006 exists to prevent: the examiner's
questions become multi-second gaps, the extractor reads them as the candidate
hesitating, and a fluent candidate is marked down for the interviewer's turns.

So clips are butt-joined instead. Clip k's words begin where clip k-1's words
ended, with no gap. Pauses *inside* an answer survive untouched, because they
are inside a single clip's own timeline and are the evidence Fluency is defined
over. Gaps *between* answers vanish, because they were never the candidate's.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
ARTIFACTS = REPO / "evals" / "speaking" / "artifacts"
DEFAULT_SIDECAR = "http://localhost:8086/stt"


def transcribe_clip(path: Path, sidecar: str) -> dict:
    """POST one clip to the sidecar and return its transcript, words and duration."""
    with path.open("rb") as handle:
        response = httpx.post(
            sidecar,
            files={"audio": (path.name, handle, "audio/wav")},
            timeout=300.0,
        )
    response.raise_for_status()
    return response.json()


def stitch(clips: list[dict]) -> dict:
    """Butt-join per-clip words into one candidate timeline.

    Returns the shape score-transcript's --stt-json expects: a duration and a
    flat word list. The duration is the SUM of the clip durations, not the span
    of the source recording -- the candidate spoke for the former, and using the
    latter would divide their words by the examiner's time too and report a
    speech rate roughly a third of the truth.
    """
    words: list[dict] = []
    offset = 0.0

    for clip in clips:
        for word in clip.get("words") or []:
            words.append({
                "word": word.get("word", ""),
                "start": round(offset + float(word.get("start", 0.0)), 4),
                "end": round(offset + float(word.get("end", 0.0)), 4),
                "confidence": word.get("confidence"),
            })
        offset += float(clip.get("duration_s") or 0.0)

    return {"duration_s": round(offset, 4), "words": words}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--sidecar", default=DEFAULT_SIDECAR)
    args = parser.parse_args()

    item_dir = ARTIFACTS / args.item_id
    clips_dir = item_dir / "clips"
    if not clips_dir.exists():
        print(f"no clips for {args.item_id}; run the clips command first", file=sys.stderr)
        return 2

    clip_paths = sorted(clips_dir.glob("*.wav"))
    if not clip_paths:
        print(f"no clip audio in {clips_dir}", file=sys.stderr)
        return 2

    results = []
    for path in clip_paths:
        try:
            payload = transcribe_clip(path, args.sidecar)
        except Exception as exc:
            # One failed clip means the stitched timeline is missing a chunk of
            # the candidate's speech, which would understate their speech rate.
            # Better to fail the item than to score a hole.
            print(f"{path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        results.append(payload)
        print(
            f"  {path.name:<28} {payload.get('duration_s', 0):>6.2f}s  "
            f"{len(payload.get('words') or []):>4} words"
        )

    stitched = stitch(results)
    (item_dir / "stt.json").write_text(
        json.dumps(stitched, indent=2) + "\n", encoding="utf-8"
    )

    transcript = " ".join(
        (r.get("transcript") or "").strip() for r in results
    ).strip()
    (item_dir / "candidate_stt.txt").write_text(transcript, encoding="utf-8")

    wpm = (
        len(stitched["words"]) / (stitched["duration_s"] / 60.0)
        if stitched["duration_s"] else 0.0
    )
    print(
        f"\n{args.item_id}: {len(clip_paths)} clips, "
        f"{stitched['duration_s']:.1f}s candidate speech, "
        f"{len(stitched['words'])} words, {wpm:.0f} wpm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

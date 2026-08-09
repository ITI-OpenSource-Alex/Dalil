"""Build a synthetic two-speaker IELTS-style recording with known ground truth.

SPEAK-EVAL-005/006 need a multi-speaker fixture to exercise diarization, role
review, clip construction and the segmentation metrics. Every real IELTS
recording carries third-party rights, and the whole point of SPEAK-EVAL-004 is
that unlicensed media does not enter this repository. So the fixture is
generated: two Windows SAPI voices reading a scripted examiner/candidate
exchange, produced by us, owned by us, with no rights attached.

The decisive advantage is not the licence, it is the ground truth. Because the
script builds the timeline turn by turn, the exact candidate and examiner
intervals are known to the millisecond. Diarization error, contamination and
boundary error can therefore be *measured* rather than eyeballed -- which is what
section 8.4 asks for and what a downloaded recording could not provide without a
manual annotation pass.

What this fixture is NOT: a substitute for real IELTS audio. Synthesised speech
has no disfluency, no natural hesitation and unnaturally clean turn boundaries,
so metrics measured on it are an upper bound on real performance, not an
estimate of it. It validates the pipeline; it cannot validate the scoring.

Usage:

    python evals/speaking/fixtures/make_two_speaker_fixture.py

Writes the WAV plus a ground-truth JSON next to this file. Requires Windows
SAPI (via PowerShell) and ffmpeg.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXAMINER_VOICE = "Microsoft David Desktop"
CANDIDATE_VOICE = "Microsoft Zira Desktop"

# A short Part 1 exchange. The candidate turns are deliberately longer than the
# examiner turns, matching a real test, so that a pipeline which accidentally
# swapped the roles would produce visibly wrong durations.
SCRIPT: list[tuple[str, str]] = [
    ("examiner", "Good morning. Can you tell me about your hometown?"),
    (
        "candidate",
        "Yes, of course. I grew up in a small city in the Nile Delta. "
        "It is a fairly quiet place, and most of the families there have known "
        "each other for generations. I still live there with my parents.",
    ),
    ("examiner", "And what do you do in your free time?"),
    (
        "candidate",
        "Well, I spend quite a lot of my free time reading, mostly history "
        "books. I also meet friends at a coffee shop near my house on Fridays, "
        "although recently I have been rather busy with work.",
    ),
    ("examiner", "Do you think you will stay there in the future?"),
    (
        "candidate",
        "That is a difficult question. Honestly, I am not sure. I would like "
        "to stay close to my family, but the opportunities in my field are "
        "mostly in the capital, so I may have to move eventually.",
    ),
]

# Silence inserted between turns, in seconds. Real conversation has a gap here
# and the pipeline must not attribute it to either speaker.
INTER_TURN_GAP_S = 0.4

SAMPLE_RATE = 16000


def _synthesise_turn(text: str, voice: str, out_path: Path) -> None:
    """Render one turn to a WAV via PowerShell SAPI."""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{voice}'); "
        f"$s.SetOutputToWaveFile('{out_path}'); "
        f"$s.Speak(@'\n{text}\n'@); "
        "$s.Dispose()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
    )


def _duration_s(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def build(out_dir: Path = HERE) -> tuple[Path, Path]:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")

    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "two_speaker_part1.wav"
    truth_path = out_dir / "two_speaker_part1.groundtruth.json"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        turn_files: list[Path] = []
        turns: list[dict] = []
        cursor = 0.0

        for index, (role, text) in enumerate(SCRIPT):
            raw = tmp_dir / f"turn_{index:02d}_raw.wav"
            norm = tmp_dir / f"turn_{index:02d}.wav"
            voice = EXAMINER_VOICE if role == "examiner" else CANDIDATE_VOICE

            _synthesise_turn(text, voice, raw)

            # Canonical form up front: mono, 16 kHz, signed 16-bit little-endian.
            # One representation for every artifact makes segmentation and
            # hashing deterministic, per section 8.3.
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw), "-ar", str(SAMPLE_RATE),
                 "-ac", "1", "-c:a", "pcm_s16le", str(norm)],
                check=True, capture_output=True,
            )

            duration = _duration_s(norm)
            turns.append({
                "turn_index": index,
                "role": role,
                "text": text,
                "start_s": round(cursor, 4),
                "end_s": round(cursor + duration, 4),
                "duration_s": round(duration, 4),
            })
            cursor += duration + INTER_TURN_GAP_S
            turn_files.append(norm)

        gap = tmp_dir / "gap.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", str(INTER_TURN_GAP_S),
             "-c:a", "pcm_s16le", str(gap)],
            check=True, capture_output=True,
        )

        concat_list = tmp_dir / "concat.txt"
        lines = []
        for index, turn_file in enumerate(turn_files):
            lines.append(f"file '{turn_file.as_posix()}'")
            if index < len(turn_files) - 1:
                lines.append(f"file '{gap.as_posix()}'")
        concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)],
            check=True, capture_output=True,
        )

    total = _duration_s(wav_path)
    truth = {
        "description": (
            "Synthetic two-speaker IELTS Part 1 exchange, generated from Windows "
            "SAPI voices. Owned by this project; no third-party rights. Turn "
            "boundaries are exact because the timeline was constructed, not "
            "annotated."
        ),
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "total_duration_s": round(total, 4),
        "inter_turn_gap_s": INTER_TURN_GAP_S,
        "voices": {"examiner": EXAMINER_VOICE, "candidate": CANDIDATE_VOICE},
        "turns": turns,
        "candidate_duration_s": round(
            sum(t["duration_s"] for t in turns if t["role"] == "candidate"), 4
        ),
        "examiner_duration_s": round(
            sum(t["duration_s"] for t in turns if t["role"] == "examiner"), 4
        ),
    }
    truth_path.write_text(
        json.dumps(truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return wav_path, truth_path


def main() -> int:
    wav_path, truth_path = build()
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    print(f"wrote {wav_path}  ({truth['total_duration_s']:.2f}s)")
    print(f"wrote {truth_path}")
    print(
        f"  candidate {truth['candidate_duration_s']:.2f}s / "
        f"examiner {truth['examiner_duration_s']:.2f}s "
        f"across {len(truth['turns'])} turns"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

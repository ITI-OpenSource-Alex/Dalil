"""GOA-133 — build matched prosody fixture pairs.

Each pair is ONE script rendered twice:

    <id>-fluent.wav    natural pace, no inserted pauses
    <id>-halting.wav   the SAME WORDS, slowed and broken by long silences

The pair is the experiment. If the Fluency and Pronunciation agents read only the
transcript, their bands must come out identical for the two files up to sampling
noise, because the transcript is identical by construction. Any difference after
GOA-133 comes from the acoustic features, which is the whole claim.

> [!IMPORTANT]
> THESE ARE SYNTHETIC. Piper TTS, not human speech. That is a real limitation and
> it is recorded in the benchmark envelope as `synthetic: true`:
>
>  - Piper's prosody is uniform, so the "fluent" arm is *more* fluent than any
>    real candidate. Absolute band values from these fixtures mean nothing.
>  - Whisper transcribes clean TTS with unusually high confidence, so
>    mean_word_confidence is optimistic and cannot be read as an intelligibility
>    figure.
>  - No disfluencies, accent, or self-correction -- exactly the phenomena the
>    Pronunciation criterion is supposed to assess.
>
> What the pairs CAN establish, and what this ticket uses them for:
>  - whether the pipeline preserves or discards timing information (exact,
>    unaffected by synthesis)
>  - whether a large, deliberate delivery difference moves the bands AT ALL
>    (directional, not calibrated)
>
> Replace with recorded human speech before quoting any band number.

Usage (needs the speech sidecar for TTS):
    docker compose up -d speech
    python perf/make_prosody_fixtures.py
"""

import io
import json
import os
import struct
import sys
import wave
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "perf" / "fixtures" / "prosody"
SPEECH_URL = os.environ.get("SPEECH_URL", "http://localhost:8086")

# IELTS Part 2 style prompts, written for this purpose so there is no licensing
# question. Split into phrases so the halting arm can insert silence at natural
# boundaries rather than mid-word.
SCRIPTS: dict[str, list[str]] = {
    "p01": [
        "I would like to talk about a journey that I took last summer.",
        "It was a trip to a small coastal town about three hours from my home.",
        "I travelled there with two friends from university.",
        "We stayed for a week in a rented apartment near the harbour.",
        "What made it memorable was the food and the people we met.",
        "I would definitely go back there again if I had the chance.",
    ],
    "p02": [
        "The skill I want to describe is learning to cook properly.",
        "I started about two years ago when I moved out of my family home.",
        "At first I could only make very simple dishes like pasta and eggs.",
        "I learned mostly from videos online and from calling my mother.",
        "Now I can prepare a full meal for six or seven people.",
        "It has saved me money and made me much healthier.",
    ],
    "p03": [
        "I want to describe a teacher who influenced me a great deal.",
        "She taught mathematics in my final two years of secondary school.",
        "What made her different was that she never simply gave us answers.",
        "She would ask a question back and wait until somebody tried.",
        "Because of her I chose to study engineering at university.",
        "I still remember her advice whenever I face a difficult problem.",
    ],
    "p04": [
        "The book I would like to talk about is one I read three times.",
        "It is a novel about a family living through a long period of change.",
        "I first read it when I was seventeen and did not understand it well.",
        "The second time I noticed how carefully the author builds each character.",
        "It taught me that patience with a difficult text is usually rewarded.",
        "I recommend it to anyone who enjoys slow and detailed storytelling.",
    ],
    "p05": [
        "I would like to describe a decision that changed my direction.",
        "Two years ago I was offered a place on a programme in another city.",
        "Accepting it meant leaving my job and most of my friends behind.",
        "I thought about it for several weeks before I finally agreed.",
        "The first months were genuinely difficult and I doubted the choice.",
        "Looking back now it was clearly the right thing to have done.",
    ],
}

# The halting arm's parameters. Chosen to be unmistakable rather than subtle: the
# question these fixtures answer is "does delivery move the band AT ALL", so a
# borderline difference would prove nothing either way.
HALTING_PAUSE_S = 1.8      # silence inserted between phrases
HALTING_SLOWDOWN = 1.35    # playback stretch factor
FLUENT_GAP_S = 0.12        # natural inter-phrase gap


def synthesise(text: str) -> tuple[bytes, int, int, int]:
    """Render one phrase via the Piper sidecar. Returns (frames, nchannels, sampwidth, framerate)."""
    response = httpx.post(f"{SPEECH_URL}/tts", json={"text": text}, timeout=120.0)
    response.raise_for_status()
    with wave.open(io.BytesIO(response.content), "rb") as wav:
        return (
            wav.readframes(wav.getnframes()),
            wav.getnchannels(),
            wav.getsampwidth(),
            wav.getframerate(),
        )


def silence(seconds: float, nchannels: int, sampwidth: int, framerate: int) -> bytes:
    return b"\x00" * int(seconds * framerate) * nchannels * sampwidth


def stretch(frames: bytes, factor: float, sampwidth: int, nchannels: int) -> bytes:
    """Slow speech by duplicating samples.

    Deliberately naive: sample duplication lowers pitch as well as rate, which a
    real slow speaker does not do. It is honest for this purpose because the
    fixture is already synthetic and the metric under test is timing, not timbre.
    A phase vocoder would produce prettier audio and no better evidence.
    """
    if factor <= 1.0:
        return frames
    frame_size = sampwidth * nchannels
    out = bytearray()
    carry = 0.0
    for i in range(0, len(frames) - frame_size + 1, frame_size):
        sample = frames[i:i + frame_size]
        carry += factor
        repeats = int(carry)
        carry -= repeats
        out += sample * repeats
    return bytes(out)


def build_pair(pair_id: str, phrases: list[str]) -> dict:
    rendered = [synthesise(p) for p in phrases]
    _, nchannels, sampwidth, framerate = rendered[0]

    fluent = bytearray()
    for idx, (frames, *_rest) in enumerate(rendered):
        if idx:
            fluent += silence(FLUENT_GAP_S, nchannels, sampwidth, framerate)
        fluent += frames

    halting = bytearray()
    for idx, (frames, *_rest) in enumerate(rendered):
        if idx:
            halting += silence(HALTING_PAUSE_S, nchannels, sampwidth, framerate)
        halting += stretch(frames, HALTING_SLOWDOWN, sampwidth, nchannels)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    durations = {}
    for name, data in (("fluent", fluent), ("halting", halting)):
        path = OUT_DIR / f"{pair_id}-{name}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(nchannels)
            wav.setsampwidth(sampwidth)
            wav.setframerate(framerate)
            wav.writeframes(bytes(data))
        durations[name] = round(len(data) / (framerate * nchannels * sampwidth), 2)

    return {
        "pair": pair_id,
        "script": " ".join(phrases),
        "fluent": f"{pair_id}-fluent.wav",
        "halting": f"{pair_id}-halting.wav",
        "fluent_duration_s": durations["fluent"],
        "halting_duration_s": durations["halting"],
        "synthetic": True,
    }


def token_overlap(a: str, b: str) -> float:
    """Jaccard over lowercased word sets. The pair is invalid below 0.95: at that
    point the two arms differ in TEXT, and any band difference measures that
    instead of delivery."""
    ta = {w.strip(".,?!").lower() for w in a.split() if w.strip(".,?!")}
    tb = {w.strip(".,?!").lower() for w in b.split() if w.strip(".,?!")}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def transcribe(path: Path) -> dict:
    with path.open("rb") as fh:
        response = httpx.post(
            f"{SPEECH_URL}/stt",
            files={"audio": (path.name, fh, "audio/wav")},
            timeout=600.0,
        )
    response.raise_for_status()
    return response.json()


def main() -> int:
    try:
        httpx.get(f"{SPEECH_URL}/health", timeout=10.0).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"speech sidecar unreachable at {SPEECH_URL}: {exc}", file=sys.stderr)
        print("start it with: docker compose up -d speech", file=sys.stderr)
        return 1

    manifest = []
    for pair_id, phrases in SCRIPTS.items():
        print(f"building {pair_id} ...", flush=True)
        entry = build_pair(pair_id, phrases)

        # Validate the pair: both arms must transcribe to the same words.
        fluent_stt = transcribe(OUT_DIR / entry["fluent"])
        halting_stt = transcribe(OUT_DIR / entry["halting"])
        overlap = token_overlap(fluent_stt["transcript"], halting_stt["transcript"])
        entry["token_overlap"] = round(overlap, 3)
        entry["fluent_transcript"] = fluent_stt["transcript"]
        entry["halting_transcript"] = halting_stt["transcript"]
        entry["valid"] = overlap >= 0.95

        status = "OK" if entry["valid"] else "INVALID"
        print(
            f"  {status}  overlap={overlap:.3f}  "
            f"fluent={entry['fluent_duration_s']}s halting={entry['halting_duration_s']}s"
        )
        manifest.append(entry)

    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    invalid = [e["pair"] for e in manifest if not e["valid"]]
    print(f"\nwrote {OUT_DIR / 'manifest.json'}")
    if invalid:
        print(f"INVALID PAIRS (token overlap < 0.95): {', '.join(invalid)}")
        print("These measure a text difference, not a delivery difference. Fix or drop them.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

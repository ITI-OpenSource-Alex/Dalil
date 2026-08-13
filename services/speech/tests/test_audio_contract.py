"""SPEAK-EVAL-002 — the sidecar must not reinterpret encoded audio as PCM.

The speaking service used to label every upload `audio/pcm;rate=16000`, and this
service decodes anything matching audio/pcm with `np.frombuffer(dtype=int16)`.
Browsers record WebM/Opus, Ogg/Opus or MP4/AAC, so a compressed container was
read as raw samples. Whisper transcribed the noise and four agents scored it.

The Go side now declares the real format. This file covers the other half: the
sidecar refuses a payload whose declared type contradicts its bytes, instead of
producing a transcript from nonsense.
"""

import io
import subprocess
import wave

import pytest
from fastapi.testclient import TestClient

from app.main import _detect_container, _suffix_for, app

client = TestClient(app)


def _tts_wav(text: str) -> bytes:
    response = client.post("/tts", json={"text": text})
    assert response.status_code == 200
    return response.content


def _transcode(wav_bytes: bytes, args: list[str]) -> bytes:
    """Re-encode WAV into a browser container using the image's ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", "pipe:0", *args, "pipe:1"],
        input=wav_bytes,
        capture_output=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"ffmpeg unavailable or failed: {proc.stderr[:200]!r}")
    return proc.stdout


def _pcm_s16le(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        return wav.readframes(wav.getnframes())


@pytest.fixture(scope="module")
def speech_wav() -> bytes:
    return _tts_wav("I travelled there with two friends from university.")


# --- the defect itself -----------------------------------------------------


def test_encoded_container_declared_as_pcm_is_rejected(speech_wav):
    """The exact production defect, at the sidecar boundary.

    Before this change the payload was accepted and frombuffer'd into noise.
    """
    webm = _transcode(
        speech_wav, ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000", "-ac", "1", "-f", "webm"]
    )

    response = client.post(
        "/stt", files={"audio": ("audio.pcm", webm, "audio/pcm;rate=16000")}
    )

    assert response.status_code == 400, (
        "a WebM container declared as raw PCM was accepted; it would decode as "
        "noise and be transcribed and scored"
    )
    assert "container" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "container,args",
    [
        ("webm", ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000", "-ac", "1", "-f", "webm"]),
        ("ogg", ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000", "-ac", "1", "-f", "ogg"]),
        # frag_keyframe+empty_moov, not +faststart: the MP4 muxer cannot write a
        # normal moov atom to a pipe ("muxer does not support non seekable
        # output"), and a fragmented MP4 is also what Safari's MediaRecorder
        # actually produces for a live recording.
        ("mp4", ["-c:a", "aac", "-b:a", "64k", "-ar", "44100", "-ac", "1",
                 "-movflags", "frag_keyframe+empty_moov", "-f", "mp4"]),
    ],
)
def test_browser_containers_transcribe_when_declared_honestly(speech_wav, container, args):
    """Every format a browser can produce must decode when labelled correctly."""
    encoded = _transcode(speech_wav, args)
    media_type = {"webm": "audio/webm", "ogg": "audio/ogg", "mp4": "audio/mp4"}[container]

    response = client.post(
        "/stt", files={"audio": (f"audio.{container}", encoded, media_type)}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"].strip(), f"{container} produced an empty transcript"
    assert body["duration_s"] > 0
    assert body["words"], f"{container} produced no word timings"


def test_encoded_and_pcm_of_the_same_speech_agree(speech_wav):
    """The strongest available check that decoding is correct rather than merely
    successful: the same utterance through two different containers must produce
    substantially the same words."""
    webm = _transcode(
        speech_wav, ["-c:a", "libopus", "-b:a", "24k", "-ar", "48000", "-ac", "1", "-f", "webm"]
    )
    pcm16k = _transcode(
        speech_wav, ["-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"]
    )

    from_webm = client.post(
        "/stt", files={"audio": ("audio.webm", webm, "audio/webm")}
    ).json()["transcript"]
    from_pcm = client.post(
        "/stt", files={"audio": ("audio.pcm", pcm16k, "audio/pcm;rate=16000")}
    ).json()["transcript"]

    def words(text: str) -> set[str]:
        return {w.strip(".,?!").lower() for w in text.split() if w.strip(".,?!")}

    a, b = words(from_webm), words(from_pcm)
    assert a and b
    overlap = len(a & b) / len(a | b)
    assert overlap >= 0.8, (
        f"WebM and PCM of the same speech disagree (overlap {overlap:.2f}):\n"
        f"  webm: {from_webm!r}\n  pcm:  {from_pcm!r}"
    )


# --- real PCM still works --------------------------------------------------


def test_real_pcm_is_still_accepted(speech_wav):
    """The integration and k6 tests send genuine PCM; that path must survive."""
    pcm = _pcm_s16le(speech_wav)

    response = client.post(
        "/stt", files={"audio": ("audio.pcm", pcm, "audio/pcm;rate=16000")}
    )

    assert response.status_code == 200, response.text
    assert response.json()["transcript"].strip()


def test_odd_length_pcm_is_rejected():
    """int16 samples come in pairs. An odd byte count is not 16-bit PCM."""
    response = client.post(
        "/stt", files={"audio": ("audio.pcm", b"\x00\x01\x02", "audio/pcm;rate=16000")}
    )
    assert response.status_code == 400


# --- malformed input -------------------------------------------------------


def test_empty_payload_is_rejected():
    response = client.post("/stt", files={"audio": ("audio.webm", b"", "audio/webm")})
    assert response.status_code == 400


def test_undecodable_payload_is_a_400_not_a_500():
    """Garbage declared as WebM is the caller's problem. A 500 would send whoever
    is on call to the wrong service."""
    response = client.post(
        "/stt",
        files={"audio": ("audio.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 512, "audio/webm")},
    )
    assert response.status_code == 400, (
        f"expected a typed client error, got {response.status_code}: {response.text[:200]}"
    )


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"\x1a\x45\xdf\xa3rest", "Matroska/WebM"),
        (b"OggS....", "Ogg"),
        (b"RIFF....WAVE", "RIFF/WAV"),
        (b"\x00\x00\x00\x20ftypM4A ", "ISO base media (MP4)"),
        (b"\x00\x01\x02\x03", None),
    ],
)
def test_detect_container(payload, expected):
    assert _detect_container(payload) == expected


@pytest.mark.parametrize(
    "declared,expected",
    [
        ("audio/webm", ".webm"),
        ("audio/webm;codecs=opus", ".webm"),
        ("audio/ogg", ".ogg"),
        ("audio/mp4", ".m4a"),
        ("audio/wav", ".wav"),
        ("application/octet-stream", ".bin"),
        ("", ".bin"),
    ],
)
def test_suffix_for(declared, expected):
    """Unknown types get .bin, not .wav. Naming an unknown payload a WAV is a
    small false claim, and small false claims are what this ticket removes."""
    assert _suffix_for(declared) == expected

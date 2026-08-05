"""GOA-133 — /stt must carry the acoustic information the agents are graded on.

Before this ticket the endpoint returned `{"transcript": ...}` and nothing else,
so the Fluency and Pronunciation agents scored criteria defined over speech rate,
pausing and intelligibility from text that contains none of it. Measured on two
renderings of one script, 18.87s and 33.67s: byte-identical STT output.

faster-whisper computed the timings on every one of those calls. The old code
discarded them on the line after they were produced.
"""

import inspect
import io
import threading
import time
import wave

import pytest
from fastapi.testclient import TestClient

from app.main import app, stt

client = TestClient(app)


def _tts(text: str) -> bytes:
    response = client.post("/tts", json={"text": text})
    assert response.status_code == 200
    return response.content


def _wav_duration_s(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


@pytest.fixture(scope="module")
def sample() -> dict:
    audio = _tts(
        "I would like to talk about a journey that I took last summer. "
        "It was a trip to a small coastal town about three hours from my home."
    )
    response = client.post("/stt", files={"audio": ("test.wav", audio, "audio/wav")})
    assert response.status_code == 200
    return {"audio": audio, "body": response.json()}


def test_stt_returns_word_timestamps(sample):
    words = sample["body"].get("words")
    assert words, "no words array: the agents have nothing to measure delivery from"

    for word in words:
        assert {"word", "start", "end", "probability"} <= set(word)
        assert word["end"] >= word["start"], f"negative-length word: {word}"
        assert 0.0 <= word["probability"] <= 1.0, f"probability out of range: {word}"

    starts = [w["start"] for w in words]
    assert starts == sorted(starts), "word start times are not monotonically ordered"


def test_stt_returns_duration_close_to_the_audio(sample):
    reported = sample["body"]["duration_s"]
    actual = _wav_duration_s(sample["audio"])
    assert reported == pytest.approx(actual, rel=0.05), (
        f"reported {reported}s against an actual {actual}s; the transcription_ratio "
        f"SLO divides by this number"
    )


def test_stt_returns_segments(sample):
    segments = sample["body"].get("segments")
    assert segments
    for segment in segments:
        assert segment["end"] >= segment["start"]
        assert isinstance(segment["text"], str)


def test_stt_response_is_backwards_compatible(sample):
    """A client reading only `transcript` must keep working against a redeployed
    sidecar. The Go service is not deployed atomically with this one."""
    body = sample["body"]
    assert isinstance(body["transcript"], str)
    assert body["transcript"].strip()


def test_words_reconstruct_the_transcript(sample):
    """Guards against the generator bug: `segments` can only be iterated once, so
    materialising it in the wrong place yields a populated transcript and an empty
    words array -- which looks like a model problem and is not."""
    body = sample["body"]
    joined = "".join(w["word"] for w in body["words"]).strip()
    assert joined.lower().replace(" ", "")[:40] == (
        body["transcript"].lower().replace(" ", "")[:40]
    )


def test_stt_handler_is_not_async():
    """Regression guard, and it will look like a mistake to whoever finds it.

    `whisper_model.transcribe()` is synchronous and CPU-bound. Inside an
    `async def` it runs on the event loop and blocks every other request in the
    process, including /health -- GOA-032 recorded the sidecar at 393% CPU with
    an unanswered health check, which no liveness probe would ever restart.
    A plain `def` is dispatched to the threadpool instead.
    """
    assert not inspect.iscoroutinefunction(stt), (
        "/stt must stay a sync handler so FastAPI offloads it to the threadpool"
    )


def test_health_answers_during_transcription():
    """The behavioural half of the test above."""
    audio = _tts(
        "This is a deliberately longer utterance so that transcription is still "
        "running while the health check is issued against the same process."
    )

    errors: list[Exception] = []

    def transcribe():
        try:
            client.post("/stt", files={"audio": ("test.wav", audio, "audio/wav")})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=transcribe)
    worker.start()
    try:
        time.sleep(0.2)  # let transcription get under way
        started = time.perf_counter()
        response = client.get("/health")
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        worker.join()

    assert not errors, errors
    assert response.status_code == 200
    assert elapsed_ms < 500, (
        f"/health took {elapsed_ms:.0f}ms while transcribing; the event loop is "
        f"blocked and a liveness probe would kill or ignore this container"
    )


def test_delivery_difference_survives_transcription():
    """The end-to-end point of this ticket, at the sidecar boundary.

    Same words, different delivery. The transcripts may match; the reported
    duration and word timings must not, or there is nothing downstream can use.
    """
    text = "I travelled there with two friends from university."
    fast = _tts(text)

    # Stretch by duplicating frames -- a crude slowdown, sufficient to prove the
    # timings differ.
    with wave.open(io.BytesIO(fast), "rb") as wav:
        params = wav.getparams()
        frames = wav.readframes(wav.getnframes())
    frame_size = params.sampwidth * params.nchannels
    stretched = b"".join(
        frames[i:i + frame_size] * 2 for i in range(0, len(frames) - frame_size + 1, frame_size)
    )
    slow_buf = io.BytesIO()
    with wave.open(slow_buf, "wb") as wav:
        wav.setparams(params)
        wav.writeframes(stretched)
    slow = slow_buf.getvalue()

    fast_body = client.post("/stt", files={"audio": ("f.wav", fast, "audio/wav")}).json()
    slow_body = client.post("/stt", files={"audio": ("s.wav", slow, "audio/wav")}).json()

    assert slow_body["duration_s"] > fast_body["duration_s"] * 1.5, (
        "the stretched audio did not report a longer duration; delivery is being "
        "flattened before it reaches any agent"
    )
    assert slow_body["words"] and fast_body["words"]
    assert slow_body["words"][-1]["end"] > fast_body["words"][-1]["end"]

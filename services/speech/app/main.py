import io
import os
import tempfile
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from faster_whisper import WhisperModel
from piper import PiperVoice
import wave

app = FastAPI()

print("Loading Whisper model...")
whisper_model = WhisperModel("small", device="cpu", compute_type="int8")

print("Loading Piper TTS model...")
piper_voice = PiperVoice.load("/models/en_US-lessac-medium.onnx")

class TTSRequest(BaseModel):
    text: str


# Container magic numbers, used only to catch a payload whose declared type
# contradicts its bytes. This is not format detection -- the declared type is
# still what decides the decode path -- it is a lie detector for the one branch
# that cannot verify itself.
_CONTAINER_SIGNATURES = (
    (b"\x1a\x45\xdf\xa3", "Matroska/WebM"),
    (b"OggS", "Ogg"),
    (b"RIFF", "RIFF/WAV"),
    (b"ID3", "MP3"),
    (b"fLaC", "FLAC"),
)

_SUFFIX_BY_MEDIA_TYPE = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}


def _detect_container(data: bytes) -> str | None:
    """Name the container this payload starts with, if it is a known one."""
    for signature, name in _CONTAINER_SIGNATURES:
        if data.startswith(signature):
            return name
    # ISO base media (MP4/M4A) puts a size field first, then 'ftyp'.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "ISO base media (MP4)"
    return None


def _suffix_for(declared: str) -> str:
    """Temp-file suffix matching the declared media type.

    Falls back to .bin rather than .wav: an unknown payload is not a WAV, and
    naming it one is a small false claim of the kind this ticket exists to
    remove. ffmpeg sniffs content, so the suffix costs nothing but honesty.
    """
    media_type = declared.split(";")[0].strip()
    return _SUFFIX_BY_MEDIA_TYPE.get(media_type, ".bin")


# GOA-133. `def`, not `async def`.
#
# whisper_model.transcribe() is synchronous and CPU-bound. Called inside an
# `async def` handler it runs ON the event loop, blocking every other request in
# the process for the whole transcription -- including /health. GOA-032's 50-VU
# run recorded the consequence: the container sat at 393% CPU with /health
# unanswered, so a container-liveness probe would never have restarted it.
#
# A plain `def` handler is dispatched to FastAPI's threadpool instead, which
# leaves the loop free to answer health checks while transcription proceeds.
# Two characters, and it is the difference between a busy service and one that
# looks dead to its orchestrator.
#
# The file is read via `audio.file` (the underlying SpooledTemporaryFile) rather
# than `await audio.read()`, which is unavailable in a sync handler.
@app.post("/stt")
def stt(audio: UploadFile = File(...)):
    data = audio.file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Empty audio payload")

    declared = (audio.content_type or "").lower()

    if "audio/pcm" in declared:
        # SPEAK-EVAL-002. Raw PCM is headerless, so this branch cannot verify
        # what it was given -- it can only trust the label. That is precisely how
        # the original defect worked: the speaking service asserted audio/pcm for
        # every session, browsers actually record WebM/Opus, and a compressed
        # container reinterpreted as int16 samples is noise. Whisper transcribed
        # the noise and four agents scored it.
        #
        # A container signature in a payload declared as raw PCM is therefore a
        # hard error, not something to work around. It means a caller is lying
        # about its bytes, and guessing on its behalf would restore the defect.
        container = _detect_container(data)
        if container:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Payload declared as {declared} but begins with a {container} "
                    f"container signature. Raw PCM is headerless; declaring an "
                    f"encoded container as PCM makes it decode as noise."
                ),
            )
        if len(data) % 2:
            raise HTTPException(
                status_code=400,
                detail="Raw 16-bit PCM must contain an even number of bytes",
            )
        audio_input = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        # Encoded audio: WebM/Opus (Chrome), Ogg/Opus (Firefox), MP4/AAC
        # (Safari), WAV, MP3. faster-whisper decodes these through ffmpeg, which
        # this image installs.
        #
        # The suffix follows the declared type rather than always being ".wav".
        # ffmpeg sniffs content and would cope either way, but a temp file whose
        # name contradicts its bytes is exactly the kind of small lie that made
        # the original defect survive review.
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=_suffix_for(declared)
        ) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        audio_input = tmp_path

    try:
        # GOA-133: word_timestamps=True.
        #
        # Two of the four IELTS speaking criteria are defined over acoustics:
        # Fluency and Coherence assesses "rate of speech, pauses, hesitation",
        # and Pronunciation assesses intelligibility. Both agents received a bare
        # transcript, because this function computed per-segment and per-word
        # timings and then threw all of them away on the next line:
        #
        #     transcript = "".join([segment.text for segment in segments]).strip()
        #
        # Measured: two recordings of the identical script, 18.87s and 33.67s,
        # produced byte-identical STT output. Whatever the agents did with that,
        # it was not assessing delivery.
        #
        # `info` also carries the audio duration, which the Go side previously had
        # to infer for its transcription_ratio SLO (GOA-032).
        try:
            segments, info = whisper_model.transcribe(audio_input, word_timestamps=True)
        except HTTPException:
            raise
        except Exception as exc:
            # SPEAK-EVAL-002: a payload ffmpeg cannot decode is the caller's
            # problem, not ours, and it must surface as a typed 400 rather than
            # a 500. A 500 reads as "the sidecar is broken" and sends whoever is
            # on call to the wrong service.
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Could not decode audio declared as "
                    f"{declared or 'an unspecified type'}: {exc}"
                ),
            ) from exc

        # `segments` is a generator: it must be materialised once and reused, or
        # the second pass over it yields nothing and the words array comes back
        # empty for reasons that look like a model problem.
        collected = list(segments)

        transcript = "".join(segment.text for segment in collected).strip()

        words = [
            {
                "word": word.word,
                "start": round(word.start, 3),
                "end": round(word.end, 3),
                # Whisper's per-word confidence. Not a pronunciation score --
                # it is the model's certainty about the token -- but it is the
                # only intelligibility signal available without forced alignment,
                # and it is a real measurement rather than an inference from text.
                "probability": round(word.probability, 4),
            }
            for segment in collected
            for word in (segment.words or [])
        ]

        return {
            # Unchanged, and first: an older client that reads only this key keeps
            # working against a redeployed sidecar.
            "transcript": transcript,
            "duration_s": round(info.duration, 3),
            "language": info.language,
            "language_probability": round(info.language_probability, 4),
            "segments": [
                {
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": segment.text,
                }
                for segment in collected
            ],
            "words": words,
        }
    finally:
        if isinstance(audio_input, str) and os.path.exists(audio_input):
            os.remove(audio_input)

@app.post("/tts")
def tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        piper_voice.synthesize_wav(req.text, wav_file)

    buffer.seek(0)
    return StreamingResponse(buffer, media_type="audio/wav")

@app.get("/health")
def health():
    return {"status": "ok"}

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

    if audio.content_type and "audio/pcm" in audio.content_type.lower():
        # Decode raw PCM (16kHz 16-bit little endian)
        audio_input = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        # Write to temp file and let faster-whisper handle decoding (e.g. WAV, MP3)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
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
        segments, info = whisper_model.transcribe(audio_input, word_timestamps=True)

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

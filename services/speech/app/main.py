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

@app.post("/stt")
async def stt(audio: UploadFile = File(...)):
    data = await audio.read()
    
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
        segments, info = whisper_model.transcribe(audio_input)
        transcript = "".join([segment.text for segment in segments]).strip()
        return {"transcript": transcript}
    finally:
        if isinstance(audio_input, str) and os.path.exists(audio_input):
            os.remove(audio_input)

@app.post("/tts")
async def tts(req: TTSRequest):
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

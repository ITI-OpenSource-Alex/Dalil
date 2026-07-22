from fastapi.testclient import TestClient
from app.main import app
import io
import wave
import time

client = TestClient(app)

def test_tts_returns_playable_audio():
    response = client.post("/tts", json={"text": "This is a test of the text to speech system."})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    
    # Verify it is a valid wav
    wav_bytes = io.BytesIO(response.content)
    with wave.open(wav_bytes, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getnframes() > 0

def test_stt_transcribes_fixture_wav():
    # Generate an audio fixture using TTS
    response = client.post("/tts", json={"text": "Hello world."})
    assert response.status_code == 200
    
    # Send it to STT
    audio_file = {"audio": ("test.wav", response.content, "audio/wav")}
    
    start_time = time.time()
    stt_resp = client.post("/stt", files=audio_file)
    latency = time.time() - start_time
    
    assert stt_resp.status_code == 200
    transcript = stt_resp.json().get("transcript", "").lower()
    
    assert "hello" in transcript
    assert "world" in transcript

def test_stt_latency_recorded():
    # Simple check that we can measure the latency
    response = client.post("/tts", json={"text": "Short."})
    audio_file = {"audio": ("test.wav", response.content, "audio/wav")}
    
    start_time = time.time()
    stt_resp = client.post("/stt", files=audio_file)
    latency = time.time() - start_time
    
    assert stt_resp.status_code == 200
    assert latency > 0
    # Latency should be recorded and reasonable
    assert latency < 10.0  # CPU inference shouldn't take more than 10s for "Short."

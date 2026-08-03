FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg wget && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download piper voice
RUN mkdir -p /models && \
    wget -qO /models/en_US-lessac-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx && \
    wget -qO /models/en_US-lessac-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

COPY app/ ./app/

# Pre-download whisper model
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8086"]

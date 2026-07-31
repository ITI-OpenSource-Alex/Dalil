# Debian slim, not Alpine. GOA-033 added sentence-transformers, which pulls PyTorch,
# and PyTorch publishes no musl wheels -- loading it on Alpine failed with
#   Error relocating .../libgomp-a34b3233.so.1: acc_async_test_all:
#   initial-exec TLS resolves to dynamic definition
# The re-ranker then degraded to a token-overlap fallback SILENTLY, so the service
# reported re-ranking as enabled while running something else entirely. Hand-installing
# libgomp / gcompat / LD_PRELOAD shims into the running container fixes nothing: it does
# not survive a rebuild and does not exist in CI or staging. The ingestion service
# already uses slim, so this is the project's existing pattern, not a new one.
FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the cross-encoder into the image. Left to first use it is a ~90 MB download
# from huggingface.co inside the first user request, in an environment that may have
# no egress at all. HF_HOME must be set before the download so the weights land where
# the runtime will look for them.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" \
    && python -c "import torch; print('torch', torch.__version__)"

# Dev target
FROM base AS dev
EXPOSE 8084
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8084", "--reload"]

# Production target
FROM base AS prod
COPY . .
EXPOSE 8084
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8084"]
# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

COPY services/writing/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY services/writing/app ./app
COPY services/writing/migrations ./migrations
COPY packages/contracts/py /packages/contracts/py

ENV PYTHONPATH=/app:/packages/contracts/py

CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

COPY services/writing/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl rpm \
    && curl -fsSLo /tmp/lambda-insights-extension.rpm https://lambda-insights-extension.s3-ap-northeast-1.amazonaws.com/amazon_linux/lambda-insights-extension.rpm \
    && rpm -U --nodeps /tmp/lambda-insights-extension.rpm \
    && rm -f /tmp/lambda-insights-extension.rpm \
    && apt-get purge -y --auto-remove curl rpm \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Shared security primitives (GOA-034). Outside /app because compose
# mounts over app/ in dev and would hide anything copied there.
COPY packages/security/py /opt/goa

COPY services/writing/app ./app
COPY services/writing/cv_processor ./cv_processor
COPY services/writing/migrations ./migrations
COPY packages/contracts/py /packages/contracts/py

ENV PYTHONPATH=/app:/packages/contracts/py:/opt/goa

CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

COPY services/writing/requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: base -- shared OS packages and installed dependencies, no app code.
FROM python:3.12-slim AS base

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
COPY packages/contracts/py /packages/contracts/py

ENV PYTHONPATH=/app:/packages/contracts/py:/opt/goa


# Stage 3a: dev -- app/cv_processor/migrations come from docker-compose's
# volume mounts, not COPY (see the writing/cv-processor services in
# docker-compose.yml), and --reload picks up live edits to them. Every other
# Python service (exam, orchestration, rag) already has this dev/prod split;
# writing did not, which meant a code change here silently never took effect
# in the running container until someone thought to rebuild it from scratch --
# exactly what produced a 405 on GET /essays after that route was added
# without an accompanying restart.
FROM base AS dev
EXPOSE 8000
CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app"]


# Stage 3b: prod -- bakes the code in, no reload.
FROM base AS prod
COPY services/writing/app ./app
COPY services/writing/cv_processor ./cv_processor
COPY services/writing/migrations ./migrations
EXPOSE 8000
CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

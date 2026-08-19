FROM python:3.11-alpine AS base

WORKDIR /app

RUN set -eux; \
    for attempt in 1 2 3; do \
        apk add --no-cache \
            gcc \
            musl-dev \
            postgresql-dev \
            libffi-dev \
            g++ \
            tesseract-ocr \
            tesseract-ocr-data-eng \
            poppler-utils \
        && break; \
        if [ "$attempt" -eq 3 ]; then exit 1; fi; \
        sleep 5; \
    done
ENV TESSDATA_PREFIX=/usr/share/tessdata

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dev target
FROM base AS dev
EXPOSE 8085
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085", "--reload", "--reload-dir", "app"]

# Production target
FROM base AS prod
COPY . .
EXPOSE 8085
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]

FROM python:3.11-alpine AS base

WORKDIR /app

RUN apk add --no-cache gcc musl-dev postgresql-dev libffi-dev g++
RUN apk add --no-cache tesseract-ocr tesseract-ocr-data-eng poppler-utils
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

FROM python:3.11-alpine AS base

WORKDIR /app

RUN apk add --no-cache gcc musl-dev postgresql-dev libffi-dev g++

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Dev target
FROM base AS dev
EXPOSE 8083
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083", "--reload"]

# Production target
FROM base AS prod
COPY . .
EXPOSE 8083
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
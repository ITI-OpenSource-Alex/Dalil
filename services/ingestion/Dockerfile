# We use the official python 3.11 slim image
FROM python:3.11-slim

WORKDIR /app

# 1. Install pip dependencies first to cache this layer
COPY services/ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Install Playwright browser and OS dependencies
# This is the heavy step that we want cached!
RUN playwright install --with-deps chromium

# 3. Copy the rest of the application code
COPY services/ingestion/ .

# 4. The shared event contracts.
#
# app/workers/scholarship_matcher.py imports `from contracts.events import ...`,
# added when GOA-023 made the producer use the shared models instead of building
# dicts by hand. Nothing put that package in the image, so the worker failed with
# ModuleNotFoundError: No module named 'contracts' the moment it ran from a built
# image. It went unnoticed because the worker is normally driven from the host,
# where the repo root is already on sys.path.
#
# Verified before this change:
#   docker compose run --rm ingestion python -c "from contracts.events import *"
#   -> ModuleNotFoundError: No module named 'contracts'
#
# This is why the build context is the repository root -- see
# .github/workflows/deploy-ingestion.yml and docker-compose.yml.
COPY packages/contracts/py/contracts ./contracts

# We'll override this CMD in docker-compose or during manual runs, 
# but this is a good default entrypoint for a python service.
CMD ["python", "handler.py", "--consume-queue"]

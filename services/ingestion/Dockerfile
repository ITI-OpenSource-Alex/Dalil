# We use the official python 3.11 slim image
FROM python:3.11-slim

WORKDIR /app

# 1. Install pip dependencies first to cache this layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Install Playwright browser and OS dependencies
# This is the heavy step that we want cached!
RUN playwright install --with-deps chromium

# 3. Copy the rest of the application code
COPY . .

# We'll override this CMD in docker-compose or during manual runs, 
# but this is a good default entrypoint for a python service.
CMD ["python", "handler.py"]
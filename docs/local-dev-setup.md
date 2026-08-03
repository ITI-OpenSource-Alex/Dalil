# Local Development Setup Guide

Follow this guide to set up the GOA microservice stack locally on your machine.

---

## Prerequisites

Make sure you have the following installed:
* **Docker & Docker Compose** (Desktop or Engine)
* **Git**
* **curl** (for endpoint testing)

---

## Step-by-Step Setup

### 1. Clone the Repository
```bash
git clone https://github.com/ITI-OpenSource-Alex/GOA.git
cd GOA
```

### 2. Configure Environment Variables
Copy the `.env.example` template files in the root folder or within each service directory to `.env`:
```bash
cp .env.example .env
cp services/orchestration/.env.example services/orchestration/.env
cp services/rag/.env.example services/rag/.env
cp services/speaking/.env.example services/speaking/.env
cp services/gateway/.env.example services/gateway/.env
cp services/writing/.env.example services/writing/.env
```
Fill in the credentials (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`) if you have them. For offline development, mock values can be used.

### 3. Spin up the Stack
Run the following command to download images, build container layers, and start the system in the background:
```bash
docker compose up -d
```
This starts:
1. `postgres` (RAG and user databases)
2. `redis-gateway` and `redis-cache` (session store and access token blacklist)
3. `localstack` (S3 & SQS emulation)
4. `prometheus` & `grafana` (monitoring metrics)
5. All 9 core GOA services

---

## Verifying the Setup

### Check Container Status
```bash
docker compose ps
```
All containers should display a status of `Up` or `healthy`.

### Check Monitoring Ports
* **Grafana Portal**: Visit `http://localhost:3001` (Username: `admin` / Password: `admin`).
* **Prometheus Scraping Status**: Visit `http://localhost:9090/targets` to verify all `/metrics` are scraping correctly.
* **LocalStack Status**: Run `curl http://localhost:4566/_localstack/health` to confirm S3 and SQS statuses are `available`.

---

## Running Test Suites

You can execute the test suites directly inside the running service containers:

```bash
# 1. Orchestration Service (Python/Pytest)
docker compose exec orchestration pytest

# 2. RAG Service (Python/Pytest)
docker compose exec rag pytest

# 3. Speaking Service (Go/Testing)
docker compose exec speaking go test ./...

# 4. Gateway Service (Go/Testing)
docker compose exec gateway go test ./...

# 5. User Service (TypeScript/Jest)
docker compose exec user npm run test
```

---

## Exam Service: Seeding the Question Bank

The Exam Service's question database starts empty. To seed it with Cambridge IELTS test questions (Stage 3 DB ingestion), follow these steps:

1. **Verify PostgreSQL is Running**: Make sure the Docker database container is up (`docker compose up -d`).
2. **Configure Database Connection**: Set the `DATABASE_URL` pointing to localhost's `exam_db`:
   - **Windows (PowerShell)**:
     ```powershell
     $env:DATABASE_URL="postgresql://goa:goa_pass@localhost:5432/exam_db"
     ```
   - **Linux/macOS (bash)**:
     ```bash
     export DATABASE_URL="postgresql://goa:goa_pass@localhost:5432/exam_db"
     ```
3. **Run Ingestion**: From the `services/exam/` directory, run the ingestion script using the Python environment:
   - **Windows**:
     ```powershell
     cd services/exam
     # Initialize python virtualenv if needed:
     python -m venv .venv
     .\.venv\Scripts\python.exe -m pip install -r requirements.txt
     .\.venv\Scripts\python.exe scripts/ingest_books.py
     ```
   - **Linux/macOS**:
     ```bash
     cd services/exam
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     python scripts/ingest_books.py
     ```

To verify that the questions successfully ingested, run:
```bash
curl -H "X-Internal-API-Key: supersecret_internal_key_123" http://localhost:8085/internal/question-bank/stats
```
Expected response:
```json
{
  "academic": { "reading": 20, "listening": 20 },
  "general": { "reading": 20, "listening": 20 }
}
```

---

## Architecture Decision: Gateway vs. Direct Calls

* **Local Development**: For simplicity, the frontend directly queries the Exam Service on port `8085` (using the `NEXT_PUBLIC_EXAM_API_URL` environment variable). This bypasses the API Gateway for local ease-of-use.
* **Production**: In staging and production, the frontend routes all requests through the public ALB/Gateway (e.g., `/api/exam/*`). The gateway validates JWT authentication and forwards requests internally to the Exam Service, preventing the Exam port from being exposed publicly. See GOA-071 for routing details and ADR 0002 for more context.


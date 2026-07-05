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
cp services/orchestration/.env.example services/orchestration/.env
cp services/rag/.env.example services/rag/.env
cp services/speaking/.env.example services/speaking/.env
cp services/gateway/.env.example services/gateway/.env
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

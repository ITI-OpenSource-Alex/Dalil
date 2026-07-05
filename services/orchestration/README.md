# Orchestration Service

The Orchestration service is a FastAPI application that acts as the central coordinator (Supervisor). It classifies the user's intent using Claude (Anthropic), loads session memory from Redis, routes queries to downstream services (RAG, Speaking, Writing), and streams responses back to clients using Server-Sent Events (SSE).

---

## What it Owns

* **Responsibility**: Intent classification, request routing/coordination, session history state management, and downstream circuit breaker fallback handling.
* **Database**: Uses `redis-cache` (logical db 1) to cache conversation turns (`ConversationBufferWindowMemory`).
* **Queues**: N/A.

---

## API Reference

### 1. `POST /chat`
* **Auth Required**: Yes (Propagates user details)
* **Request Shape**:
```json
{
  "userId": "usr_abc123",
  "sessionId": "session_xyz",
  "message": "Can you check if there are scholarships for Computer Science?"
}
```
* **Response Shape (200 OK - SSE Stream)**:
  * **Event 1**: `metadata` - Returns classified intent.
    ```json
    data: {"type": "metadata", "intent": "RAG", "confidence": 0.95}
    ```
  * **Event 2+**: `token` - Streaming text chunks from the downstream handler.
    ```json
    data: {"type": "token", "content": "Here "}
    ```
* **Error Codes**:
  * `422 Unprocessable Entity`: Missing fields.
  * `200 OK` with `token` error message (on downstream failure/timeout):
    ```json
    data: {"type": "token", "content": "I'm sorry, but the RAG service is currently offline. Please try again later."}
    ```

### 2. `GET /sessions/:sessionId/history`
* **Response Shape (200 OK)**:
```json
[
  {"role": "user", "content": "Can you check if there are scholarships for Computer Science?"},
  {"role": "assistant", "content": "Yes, DAAD offers a scholarship for computer science..."}
]
```

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | FastAPI server port binding. | `8083` |
| `REDIS_URL` | Redis URL specifying db=1 for cache memory storage. | `redis://redis-cache:6379/1` |
| `ANTHROPIC_API_KEY` | Anthropic API key used for intent classification. | `mock-key` |
| `RAG_SERVICE_URL` | Downstream connection URL for the RAG service. | `http://rag:8084` |
| `SPEAKING_SERVICE_URL`| Downstream connection URL for the Speaking service. | `http://speaking:8082` |
| `WRITING_SERVICE_URL` | Downstream connection URL for the Writing service. | `http://writing:8000` |

---

## How to Run Locally

### Running outside Docker
Make sure to create a virtual environment first:
```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8083 --reload
```

### Running with Docker
```bash
docker compose up -d orchestration
```

---

## How to Run Tests

```bash
# Run pytest suite inside the container
docker compose exec orchestration pytest
```

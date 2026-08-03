# Orchestration Service

The Orchestration service is a FastAPI application that acts as the central coordinator (Supervisor). It classifies the user's intent using Claude (Anthropic), loads session memory from Redis, routes queries to downstream services (RAG, Speaking, Writing), and streams responses back to clients using Server-Sent Events (SSE).

---

## What it Owns

* **Responsibility**: Intent classification, request routing/coordination, session history state management, long-term user memory, and downstream circuit breaker fallback handling.
* **Database**: `redis-cache` (logical db 1) for conversation turns (`ConversationBufferWindowMemory`) and session bookkeeping; `orchestration_db` (Postgres) for long-term facts — see [Long-term memory](#long-term-memory-goa-038).
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

### 3. `DELETE /sessions/memory`

Erases everything the service remembers about the calling user: the long-term
facts **and** the short-term Redis transcripts.

* **Identity**: `X-User-Id`, set by the Gateway from a validated JWT. The
  endpoint returns `401` without it and never reads a user id from the request
  body or query string — otherwise any authenticated user could erase another
  user's memory by naming them.
* **Response Shape (200 OK)**:
```json
{"factsDeleted": 4, "sessionsCleared": 2, "factRetentionDays": 30}
```
* **Error Codes**: `401` no identity; `500` deletion failed (nothing is
  reported as deleted unless it was); `503` memory store unreachable.

---

## Long-term memory (GOA-038)

Facts a user states about themselves survive their session, so the assistant
already has context when they come back.

**What is stored** — one row per fact in `user_facts` (`orchestration_db`):
`degree`, `gpa`, `target_country`, `mentioned_program`, `concern`.

Exam band scores are **never** stored. Those are authoritative from the Exam
service via `fetch_exam_context`, and a number mentioned in passing must not
compete with a graded result. The `fact_type` CHECK constraint enforces this;
the extraction prompt merely asks.

**How it flows**

| Stage | Where | When |
| :--- | :--- | :--- |
| Session bookkeeping | `orch:session:{id}` hash, `orch:sessions:active` zset | after each turn |
| Extraction | `memory_sweep.sweep_once` → LLM → `user_facts` | sessions idle ≥ `MEMORY_IDLE_MINUTES` |
| Read back | `facts_context.fetch_user_facts` → supervisor prompt | every chat turn |
| Reaching the user | `standalone_question`, which downstream services receive | every chat turn |
| Expiry | read-time filter, plus a purge each sweep | `MEMORY_FACT_TTL_DAYS` after last reinforcement |

Facts influence the answer through `standalone_question` — the rewritten
question sent downstream. Facts placed only in the supervisor prompt would
personalise routing and nothing the user ever sees.

**Contradiction rule** (in SQL, `facts_repository.upsert_fact`):

| Incoming | Result |
| :--- | :--- |
| Same value | reinforced — expiry clock restarts, no new row |
| Different value, confidence ≥ 0.60 | replaces the stored value, `revision` + 1 |
| Different value, confidence < 0.60 | discarded — a hedge cannot evict a stated fact |

**Wiping a user's memory in local dev**

```bash
docker compose exec postgres psql -U goa -d orchestration_db \
  -c "DELETE FROM user_facts WHERE user_id = 'the-user-id';"
docker compose exec redis-cache redis-cli -n 1 DEL user_facts:the-user-id
```

**Watching the sweep run** — the production idle threshold is 30 minutes, so
lower it rather than waiting:

```bash
MEMORY_IDLE_MINUTES=1 MEMORY_SWEEP_INTERVAL_SECONDS=30 docker compose up -d orchestration
docker compose logs -f orchestration | grep memory_sweep_completed
```

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | FastAPI server port binding. | `8083` |
| `DATABASE_URL` | Postgres URL for long-term facts. Migrations run at startup. | `postgresql://goa:goa_pass@postgres:5432/orchestration_db` |
| `REDIS_URL` | Redis URL specifying db=1 for cache memory storage. | `redis://redis-cache:6379/1` |
| `ANTHROPIC_API_KEY` | Anthropic API key used for intent classification. | `mock-key` |
| `RAG_SERVICE_URL` | Downstream connection URL for the RAG service. | `http://rag:8084` |
| `SPEAKING_SERVICE_URL`| Downstream connection URL for the Speaking service. | `http://speaking:8082` |
| `WRITING_SERVICE_URL` | Downstream connection URL for the Writing service. | `http://writing:8000` |
| `EXAM_SERVICE_URL` | Downstream connection URL for the Exam service. | `http://exam:8085` |
| `MEMORY_ENABLED` | Kill switch for long-term memory. The delete endpoint stays live regardless. | `true` |
| `MEMORY_IDLE_MINUTES` | Silence before a session is considered finished. | `30` |
| `MEMORY_SWEEP_INTERVAL_SECONDS` | How often the sweep looks for idle sessions. | `300` |
| `MEMORY_SWEEP_BATCH_MAX` | Sessions extracted per sweep. Each one is a billed LLM call. | `20` |
| `MEMORY_MIN_TURNS` | Below this, a session is skipped without calling the model. | `4` |
| `MEMORY_FACT_TTL_DAYS` | Expiry, measured from last reinforcement. | `30` |
| `MEMORY_LOAD_TIMEOUT_MS` | Ceiling on the fact read in front of classification. | `250` |
| `MEMORY_CACHE_TTL_SECONDS` | Redis cache lifetime for a user's facts. | `300` |

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

The memory tests use a **real** Postgres and a **real** Redis (db 9, so a
running stack in db 1 is untouched), because what they assert — a unique index,
a CHECK constraint, an ON CONFLICT clause, a ZRANGEBYSCORE — cannot be
exercised through a fake. They fail rather than skip when neither is reachable:

```bash
docker compose up -d postgres redis-cache
```

The cassette tests in `test_facts_live.py` and `test_agentrouter.py` replay
recorded gateway responses by default — no network, no cost. Re-record after
changing `SUPERVISOR_PROMPT` or `USER_FACTS_INJECTION`:

```bash
RUN_LIVE_LLM_TESTS=1 docker compose exec orchestration pytest tests/test_facts_live.py
```

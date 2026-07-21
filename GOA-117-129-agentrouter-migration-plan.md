# AgentRouter Migration — GOA-117 → GOA-130

**Supersedes the Ollama local-inference plan.** A $150 AgentRouter quota removes the constraint that plan was built around. Frontier models are back, latency is a non-issue, and most of the Sprint 3/4 compromises are reversed.

**What this plan is:** point every LLM call at AgentRouter via the existing `anthropic` SDK, keep a small local Ollama **for embeddings only**, keep the local speech sidecar. Nine services, two languages, one base URL.

---

# How to use this document

**For antigravity (ag):**
- Every ticket has **Files touched** with verified line numbers, **Steps** as numbered imperatives, **Automated tests (you write and run these)**, and **Definition of Done**.
- Per the skeleton-mentor skill rule 7: **testing is yours end to end.** Write the tests, run them, fix what fails, iterate until green. Do not hand back a ticket with failing tests and do not ask for review of test code.
- Line numbers here were verified on 2026-07-20. If a line number does not match, **search for the quoted code snippet instead** — the snippet is authoritative, the line number is a convenience.
- Do not start a ticket whose **Dependencies** are not marked done.

**For me (the human):**
- Every ticket has a **Manual verification (I run this)** block: copy-pasteable commands with the **exact expected output** written out. If what I see does not match what is written, the ticket is not done regardless of what the test suite says.
- This project has been burned four times by green tests over a broken system. The manual block exists because mocks lie.

---

# PART 0 — E2E readiness blockers (read before planning demo scope)

Investigated 2026-07-20, read-only. **None of these are caused by the router migration** — they are pre-existing gaps that block [GOA_E2E_Integration_Test_Plan.md](GOA_E2E_Integration_Test_Plan.md) and [GOA_E2E_Testing_Tickets.md](GOA_E2E_Testing_Tickets.md). They are recorded here because this is the document you are actually reading, and because they change what the demo can honestly claim.

## 🔴 Hard blockers

### B1 — GOA-049 Cambridge content never shipped
- `services/exam/app/migrations/005_seed_writing_questions.sql` is **0 bytes**.
- No Reading or Listening question data exists anywhere in the repo.
- No `pdfplumber` / `pypdf` in the exam service dependencies — the extraction path was never built.

**Blocks:** `ENV-06`, `ENV-07`, all 12 cases of GOA-100, GOA-107's exam rubric.

### B2 — GOA-087 CV Processor Lambda does not exist
Only `services/ingestion/handler.py` exists. There is no CV processing Lambda.

**Blocks:** `CV-03`, `CV-06`, GOA-099 (`WR-06`, `WR-09`), GOA-105 (`EVT-04`, `EVT-05`).

### B3 — LocalStack provisions 3 of 6+ resources, zero DLQs
`infra/localstack/init/` contains exactly one script, `10-writing-resources.sh`, which creates only:
- `goa-writing-files`, `goa-cv-uploaded`, `goa-cv-processing`

**Missing:** `user-events` (referenced by **both** user-service and RAG), `notification-queue`, `ingestion-queue`, and every dead-letter queue.

**Blocks:** `INFRA-07`, `ENV-05`, `PROF-03`, `PROF-04`, GOA-105 (`EVT-01`, `EVT-02`, `EVT-06`).

### B4 — Speech has no provider
No ElevenLabs key, and AgentRouter is chat-only — no STT, no TTS. GOA-127's local sidecar is not built.

**Blocks:** all 7 cases of GOA-098, `FE-05`.

## 🟡 Soft blockers

| # | Finding | Consequence |
|---|---|---|
| S1 | Frontend chat components exist (10 files, ~40 KB; `chat-shell.tsx:356` calls `/api/chat`, `:100` calls `/api/chat/sessions/${sessionId}/history`) but contain **zero SSE / EventSource references** | `FE-02` (streaming) will likely fail — the backend streams, the frontend does not consume the stream |
| S2 | Notification service is an empty `.gitkeep` and is **not in docker-compose** | The stack is **8 services, not 9**. Any test asserting nine will fail |
| S3 | No `develop` branch. `dev` is 37 commits behind `Refactoring`; `GOA-020` has 23 commits not in `dev` | CI targets and E2E branch assumptions are wrong |
| S4 | RAG corpus is empty — nothing has ever been embedded | Any retrieval-quality assertion is untestable until ingestion runs (see GOA-118) |

## ✅ Confirmed ready

- GOA-112 / 113 / 114 committed (`2a8f9c2`)
- GOA-090 present: `services/gateway/handlers/auth.go`, `services/user/src/users/internal-auth.controller.ts`
- Gateway has zero `DATABASE_URL` references (correct — it must not touch the DB)
- All 7 ingestion adapters present

## What this means for scope

B1–B4 are **not in this migration's scope** and must not be silently absorbed into it. Decide explicitly, before the demo, which of the four you are fixing and which you are declaring as known limitations. B4 is partly addressed by GOA-127 in this plan; B1–B3 are not addressed anywhere in this plan.

---

# PART 1 — Verified code inventory

Every LLM and embedding call site in the repo, verified 2026-07-20. **This table is the migration's complete surface area.** If ag touches a file not on this list, something is wrong.

## LLM call sites (5 services, 6 sites)

| # | File | Line | Current code | Ticket |
|---|---|---|---|---|
| L1 | `services/orchestration/app/services/supervisor.py` | 23 | `llm = ChatAnthropic(model="claude-haiku-4-5-20251001", anthropic_api_key=settings.anthropic_api_key)` | GOA-119 |
| L2 | `services/rag/app/services/rag_service.py` | 32 | `llm = ChatAnthropic(model="claude-haiku-4-5-20251001", anthropic_api_key=anthropic_key)` | GOA-120 |
| L3 | `services/rag/app/services/llm_boost.py` | 33 | `llm = ChatAnthropic(model_name="claude-3-haiku-20240307", api_key=os.getenv("ANTHROPIC_API_KEY"), temperature=0.0)` | GOA-120 |
| L4 | `services/writing/app/agents.py` | 358 | `client = AsyncAnthropic(api_key=settings.anthropic_api_key or "not-configured", timeout=settings.anthropic_timeout_seconds)` | GOA-121 |
| L5 | `services/speaking/llm/client.go` | 28–29 | `func NewClient(model, apiKey string)` → `anthropic.NewClient(option.WithAPIKey(apiKey))` | GOA-122 |
| L6 | `services/ingestion/app/adapters/visa_adapter.py` | 123 | `self.anthropic = anthropic_client or AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))` | GOA-123 |

**Model names currently hardcoded** (all must become config-driven):
- `supervisor.py:24` → `"claude-haiku-4-5-20251001"`
- `rag_service.py:32` → `"claude-haiku-4-5-20251001"`
- `llm_boost.py:34` → `"claude-3-haiku-20240307"` ⚠️ **deprecated model, would 404 even against real Anthropic**
- `visa_adapter.py:29` → `EXTRACTION_MODEL = "claude-haiku-4-5-20251001"`
- `speaking/cmd/speaking/main.go:52` → `llm.NewClient("claude-3-5-haiku-20241022", ...)` (practice)
- `speaking/cmd/speaking/main.go:53` → `llm.NewClient("claude-sonnet-4-6", ...)` (exam)
- `writing/app/config.py:21` → `writing_model: str = "claude-sonnet-4-6"` ✅ already config-driven

## Embedding call sites (2)

| # | File | Line | Current code | Ticket |
|---|---|---|---|---|
| E1 | `services/rag/app/services/rag_service.py` | 28–30 | `embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=openai_key)` | GOA-118 |
| E2 | `services/ingestion/embedder.py` | 27–30 | `client.embeddings.create(model="text-embedding-3-small", input=batch)` | GOA-118 |

Note the RAG symbol is **`embeddings_model`**, not `embeddings`, and it is wrapped by `generate_embedding()` at `rag_service.py:35`.

## Pre-existing defects found during this audit

> [!CAUTION]
> **D1 — `docker-compose.yml:83` contains a hardcoded, real-shaped OpenAI API key** committed to the repo:
> `- OPENAI_API_KEY=sk-proj-a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4`
> Whether or not it is live, it must not stay in version control. GOA-118 removes it. If it is a real key, **revoke it.**

> [!WARNING]
> **D2 — the speaking service has no `ANTHROPIC_API_KEY` in docker-compose at all.** Its environment block (`docker-compose.yml:173–181`) sets `PORT`, `MAX_CONNECTIONS`, `ELEVENLABS_API_KEY`, `OTEL_SERVICE_NAME`, and the three Langfuse vars — nothing else. The Go service builds an Anthropic client from an empty string. GOA-122 fixes this.

> [!WARNING]
> **D3 — the ingestion service is not in docker-compose** (zero matches). It runs as a Lambda handler / standalone script. GOA-123's env vars must be set wherever it actually runs, not in compose.

> [!NOTE]
> **D4 — `llm_boost.py:34` targets `claude-3-haiku-20240307`**, a deprecated model. This call site has almost certainly never succeeded. Treat GOA-120 as a **fix**, not just a re-point.

---

# PART 2 — Provider facts

| | |
|---|---|
| **Anthropic-compatible base URL** | `https://agentrouter.org` — **no `/v1` suffix** |
| **OpenAI-compatible base URL** | `https://agentrouter.org/v1` |
| **Auth** | API key sent as a **Bearer token** (`ANTHROPIC_AUTH_TOKEN` per their docs), not the usual `x-api-key` |
| **Quota** | $150, pay-as-you-go |

> [!WARNING]
> **Do not mix the two base URLs.** Anthropic-compatible is `https://agentrouter.org`; OpenAI-compatible is `https://agentrouter.org/v1`. Using the wrong one for the wrong SDK fails confusingly.

### Models and pricing

| Model | Endpoints | Prompt /1M | Completion /1M |
|---|---|---|---|
| **`claude-opus-4-8`** ← **our pick** | anthropic + openai | **$2.00** | **$10.00** |
| `glm-5.2` | openai only | $6.00 | $9.00 |
| `gpt-5.5` | openai only | $7.00 | $14.00 |
| `claude-opus-4-6` | anthropic + openai | $8.00 | $40.00 |
| `claude-opus-4-7` | anthropic + openai | $8.00 | $40.00 |

**Why `claude-opus-4-8` everywhere:** cheapest on both axes, and Anthropic-compatible — the existing `anthropic` Python SDK and `anthropic-sdk-go` calls work with only a `base_url` change. `glm-5.2` is marginally cheaper on completion ($9 vs $10) but triples prompt cost ($6 vs $2), and this workload is long-prompt/short-completion (transcripts and essays in, compact JSON out). It is also OpenAI-endpoint-only, forcing an SDK rewrite across five services for no gain.

**No embeddings model exists on this router.** All five are chat models. Embeddings stay local.

### Budget model

| Operation | Tokens (approx) | Cost |
|---|---|---|
| Swarm evaluation (4 agents) | 6,000 prompt + 1,600 completion | **~$0.028** |
| RAG query | 2,000 prompt + 300 completion | **~$0.007** |
| Intent classification | 200 prompt + 50 completion | **~$0.001** |
| Full eval suite run (GOA-020/028) | — | **~$1.50–2.00** |

**$150 ≈ 5,000 swarm evaluations, or 75–100 full eval-suite runs.** Comfortable, not tight. Instrument it (GOA-130), but do not let budget distort design.

---

# PHASE 0 — Wire the router

## GOA-117 — Router spike and shared configuration

| | |
|---|---|
| **Service** Cross-service | **Priority** P1 (blocks everything) | **Points** 1 | **Dependencies** none |

**Summary:** Every LLM call site already uses an Anthropic SDK and AgentRouter is Anthropic-compatible, so this is a base-URL and auth change — **no proxy container, no translation layer.** But the auth mechanism is unconfirmed, and five services in two languages depend on the answer. Resolve that first, in isolation, before touching any service code.

### Step 1 — Resolve the auth mechanism (do this before anything else)

AgentRouter's docs show the key as a **Bearer token** (`ANTHROPIC_AUTH_TOKEN`). The Anthropic SDK defaults to the `x-api-key` header. The SDK's `auth_token=` parameter *should* send `Authorization: Bearer`, but this is unconfirmed against this gateway.

Run **A** first. If it 401s, run **B**.

```bash
# A — Bearer (matches the docs)
docker compose exec rag python -c "
from anthropic import Anthropic
import os, time
c = Anthropic(auth_token=os.environ['ANTHROPIC_AUTH_TOKEN'], base_url='https://agentrouter.org')
t=time.time()
m = c.messages.create(model='claude-opus-4-8', max_tokens=20,
      messages=[{'role':'user','content':'Reply with exactly: OK'}])
print('TEXT:', m.content[0].text)
print('LATENCY_S:', round(time.time()-t,2))
print('TOKENS:', m.usage.input_tokens, m.usage.output_tokens)
"
```

```bash
# B — x-api-key (only if A returned 401)
docker compose exec rag python -c "
from anthropic import Anthropic
import os
c = Anthropic(api_key=os.environ['ANTHROPIC_AUTH_TOKEN'], base_url='https://agentrouter.org')
print(c.messages.create(model='claude-opus-4-8', max_tokens=20,
      messages=[{'role':'user','content':'Reply with exactly: OK'}]).content[0].text)
"
```

**Record the winner in `docs/INFERENCE.md` immediately.** The Go equivalent is `option.WithAuthToken()` (Bearer) vs `option.WithAPIKey()` (x-api-key).

**If neither works:** fall back to the OpenAI-compatible endpoint (`https://agentrouter.org/v1`) with the OpenAI SDK. That is an SDK swap across five services — which is exactly why this spike is ten minutes now rather than a discovery on day four.

### Step 2 — Add environment variables

Add to `.env.example` and to the `environment:` block of **orchestration** (`docker-compose.yml:254` area), **rag** (`:196` area), **writing** (`:76` area), and **speaking** (`:173` area — see defect **D2**, this service currently has no Anthropic config at all):

```yaml
      - ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-}
      - ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN:-}
      - LLM_MODEL=${LLM_MODEL:-claude-opus-4-8}
```

For **ingestion** (defect **D3** — not in compose): set these wherever the handler actually runs (Lambda env config / local `.env`).

The `:-` defaults matter: an unset `ANTHROPIC_BASE_URL` must leave the system pointed at direct Anthropic.

### Step 3 — Make the model name configurable per service

Do **not** introduce one global model constant. The tickets already differentiate model choice (practice vs exam in speaking, boost vs answer in RAG) and a single constant will not survive contact. Each service reads its own `LLM_MODEL` (or a service-specific override) with `claude-opus-4-8` as the default.

### Step 4 — Preserve the escape hatch

Leave every existing code path intact. With `ANTHROPIC_BASE_URL` unset, each SDK falls back to its built-in default and the system talks to Anthropic directly. This is the demo-day fallback and it must keep working.

### Automated tests (ag writes and runs these)

1. `test_client_uses_base_url_when_env_set` — patch env with `ANTHROPIC_BASE_URL=https://example.invalid`, construct the client, assert the resulting client's base URL reflects it.
2. `test_client_falls_back_to_default_when_env_unset` — with `ANTHROPIC_BASE_URL` absent, assert the client's base URL is the Anthropic default.
3. `test_model_name_is_config_driven` — assert no bare model-name string literal survives at the call sites listed in Part 1. A grep-style assertion over the source is acceptable and is the point.
4. All existing suites in orchestration, rag, writing, ingestion stay green. `go test ./...` in speaking stays green.

### Manual verification (I run this)

```bash
docker compose exec rag env | grep -E 'ANTHROPIC_(BASE_URL|AUTH_TOKEN)|LLM_MODEL'
```
**Expect:** three lines. `ANTHROPIC_BASE_URL=https://agentrouter.org`, a non-empty `ANTHROPIC_AUTH_TOKEN`, `LLM_MODEL=claude-opus-4-8`.

Then re-run the **Step 1 A** command above.
**Expect:** `TEXT: OK`, a `LATENCY_S` under about 5, and non-zero token counts. **Write the latency down** — it sizes every timeout decision in Phase 2.

### Definition of Done
- One `messages.create` through AgentRouter returns generated text **from inside a container**.
- Auth mechanism confirmed and written into `docs/INFERENCE.md`.
- With `ANTHROPIC_BASE_URL` unset, behaviour is unchanged and all suites still pass.
- Measured latency recorded.

---

# PHASE 1 — Embeddings stay local

## GOA-118 — Ollama embeddings + pgvector re-dimension

| | |
|---|---|
| **Service** RAG + Ingestion | **Priority** P1 | **Points** 2 | **Dependencies** GOA-117 |

> [!IMPORTANT]
> **This ticket survives the router change unchanged.** AgentRouter has **no embeddings model** — all five offerings are chat models. Embeddings must run locally, so the `VECTOR(1536)` → `VECTOR(768)` migration still happens.
>
> **It is time-sensitive:** nothing has ever been embedded (there was never an OpenAI key — see blocker **S4**), so re-dimensioning is free *now* and becomes a full re-embed the moment any ingestion runs. **Do this before Phase 2.**

### Step 1 — Install Ollama and pull the model

Natively on Windows — no Docker GPU passthrough needed.

```bash
ollama pull nomic-embed-text     # 274 MB, 768 dimensions
```

This is the **only** local model now. The 4 GB VRAM constraint that dominated the old plan is irrelevant for a single 274 MB embedder.

### Step 2 — Write migration `017_reembed_dimensions.sql`

First confirm the actual index name — if it is not `documents_embedding_idx`, the `DROP INDEX IF EXISTS` silently no-ops and the `ALTER` then fails:

```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db -c "\d documents"
```

Then confirm nothing has been embedded, because the migration below **discards existing vectors**:

```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT count(*) FROM documents WHERE embedding IS NOT NULL;"
```
If this returns anything other than `0`, **stop** — you need a re-embed strategy, not a discard.

Create `services/rag/app/migrations/017_reembed_dimensions.sql`:

```sql
-- The ivfflat index is dimension-bound; it must be dropped before the type change.
DROP INDEX IF EXISTS documents_embedding_idx;

ALTER TABLE documents
ALTER COLUMN embedding TYPE vector(768) USING NULL;

CREATE INDEX documents_embedding_idx
ON documents USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

> [!CAUTION]
> **The rollback file goes in `services/rag/app/migrations/rollback/017_reembed_dimensions_down.sql` — NOT beside the migration.**
> The runner globs `migrations/*.sql` and executes everything it finds in sorted order. This is exactly how GOA-116's migration self-destructed: the runner created the table, then immediately ran the adjacent down-migration and dropped it, logging both as applied. Unrecoverable by restart.

### Step 3 — Repoint RAG embeddings

`services/rag/app/services/rag_service.py:28–30`. Ollama exposes an **OpenAI-compatible** embeddings API, so `langchain_openai` stays and no dependency changes:

```python
embeddings_model = OpenAIEmbeddings(
    model=settings.embedding_model,
    openai_api_key=settings.embedding_api_key,   # Ollama ignores it; the SDK requires non-empty
    base_url=settings.embedding_base_url,
    check_embedding_ctx_length=False,            # Ollama has no tokenizer introspection endpoint
)
```

`check_embedding_ctx_length=False` is not optional — without it `langchain_openai` tries to tokenize against an OpenAI tokenizer that does not know this model.

Update the docstring at `rag_service.py:36`, which currently says **"1536-dimensional"**.

Add to `services/rag/app/core/config.py` (the `Settings` class at line 5, which currently declares `openai_api_key: str` and `anthropic_api_key: str` as **required**):

```python
    embedding_base_url: str = "http://host.docker.internal:11434/v1"
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str = "ollama"
```

`host.docker.internal` is how a container reaches Ollama running natively on the Windows host. On Linux this needs `extra_hosts: ["host.docker.internal:host-gateway"]` in compose.

**Remove the now-unused required `openai_api_key: str`** — and with it the hardcoded key at `docker-compose.yml:83` (defect **D1**).

### Step 4 — Repoint ingestion embeddings

`services/ingestion/embedder.py`:
- `:7–9` `get_openai_client()` → `OpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_base_url)`
- `:28` `model = "text-embedding-3-small"` → `model = settings.embedding_model`
- `:13` the docstring names the old model — update it.
- `:34` the error log says `"OpenAI embeddings generation failed"` — reword; it will now be misleading.

Batching at `:21` (`batch_size = 100`) is an OpenAI rate-limit optimization. Ollama has no such limit but also no harm from it — leave it.

### Step 5 — Add settings in *both* places

Add the three embedding settings to `docker-compose.yml` **and** to the test `conftest.py` files. **This project has broken twice from adding a setting in only one place** (exam's missing `WRITING_SERVICE_URL`, exam's missing `SPEAKING_SERVICE_URL`).

### Automated tests (ag writes and runs these)

1. `test_embedding_dimension_is_768` — call `generate_embedding("test")`, assert `len(...) == 768`. Integration test; mark it so CI can skip if Ollama is absent, but **it must actually run locally**.
2. `test_embeddings_client_targets_configured_base_url` — assert the client points at `settings.embedding_base_url`, not `api.openai.com`.
3. `test_no_openai_model_names_remain` — assert `text-embedding-3-small` appears nowhere in `services/rag/` or `services/ingestion/`.
4. `test_migration_017_is_idempotent` — apply twice, assert no error and exactly one `migrations_log` row.
5. `test_rollback_not_in_migrations_glob` — assert the `migrations/*.sql` glob does **not** match anything under `rollback/`. Regression guard for the GOA-116 self-destruction.
6. Existing RAG suite green.

### Manual verification (I run this)

**1. Ollama is alive and the model is present:**
```bash
ollama list | grep nomic-embed-text
```
**Expect:** one line naming `nomic-embed-text` at roughly 274 MB.

**2. The migration applied and stayed applied across a restart:**
```bash
docker compose restart rag && sleep 15
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT migration_file FROM migrations_log WHERE migration_file LIKE '017%';"
```
**Expect:** exactly one row, `017_reembed_dimensions.sql`. **Zero rows means it never ran; two rows means the ledger is broken.**

**3. The column is genuinely 768-dimensional:**
```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT atttypmod FROM pg_attribute WHERE attrelid='documents'::regclass AND attname='embedding';"
```
**Expect:** `768` (pgvector stores the dimension in `atttypmod` directly). If it says `1536`, the ALTER did not take.

**4. The service produces a real 768-dim vector:**
```bash
docker compose exec rag python -c "
import asyncio
from app.services.rag_service import generate_embedding
v = asyncio.run(generate_embedding('student visa requirements'))
print('dims:', len(v)); print('first3:', [round(x,4) for x in v[:3]])
assert len(v) == 768, f'GOT {len(v)}'
print('PASS')
"
```
**Expect:** `dims: 768`, three plausible floats (**not** all zeros), then `PASS`.

**5. The RAG container did not crash-loop:**
```bash
docker compose ps rag
```
**Expect:** `Up`, **not** `Restarting`. This project has had three separate migration-induced crash-loops; check it every time.

### Definition of Done
- Migration applies and **stays** applied across a restart (`migrations_log` row present, `atttypmod` is 768).
- `generate_embedding()` returns 768 floats.
- Ingestion writes 768-dim embeddings.
- `POST /query` returns a grounded answer with sources.
- No `text-embedding-3-small` and no hardcoded OpenAI key remain anywhere.

---

# PHASE 2 — Call sites

All five services already speak an Anthropic SDK, so each ticket is a config change plus verification. **The timeout inflation, output-token cuts, and serialization workarounds from the Ollama plan are all deleted** — frontier models are fast and genuinely parallel.

**Cross-cutting DoD requirement:** every ticket requires **3 consecutive clean runs**. Frontier models are far more reliable at strict JSON than 3B models, so the 5-run bar is relaxed — but not to one.

---

## GOA-119 — Orchestration supervisor

| | |
|---|---|
| **Service** Orchestration | **Priority** P1 | **Points** 1 | **Dependencies** GOA-117 |

**Files:** `services/orchestration/app/services/supervisor.py:23`, `services/orchestration/app/core/config.py:9`

### Steps
1. `config.py` currently declares only `anthropic_api_key: str` at line 9. Add `anthropic_base_url: str = ""` and `llm_model: str = "claude-opus-4-8"`.
2. `supervisor.py:23–26` — replace the hardcoded model and add the base URL:
   ```python
   llm = ChatAnthropic(
       model=settings.llm_model,
       anthropic_api_key=settings.anthropic_api_key,
       **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
   )
   ```
   The conditional-kwarg form preserves the GOA-117 escape hatch: unset base URL → SDK default.
3. If GOA-117's spike concluded **Bearer**, `ChatAnthropic` may need the token via `default_headers={"Authorization": f"Bearer {token}"}` rather than `anthropic_api_key`. **Verify this specific client** — `langchain_anthropic` wraps the SDK and does not always expose `auth_token`.
4. `structured_llm = llm.with_structured_output(IntentResult)` at `:27` must keep working. Structured output relies on tool-use; if AgentRouter does not forward tool definitions, this breaks. **Test it explicitly — it is the highest-risk item in this ticket.**
5. Do not touch the circuit breaker configuration.

### Automated tests (ag writes and runs these)
1. `test_all_five_intents_classify_correctly` — one representative utterance per intent. Run 3×.
2. `test_structured_output_returns_intentresult_instance` — asserts the `with_structured_output` path returns a parsed model, not a raw string. **This is the tool-use passthrough guard.**
3. `test_base_url_omitted_when_setting_empty` — assert `ChatAnthropic` is constructed without a `base_url` kwarg when the setting is `""`.
4. `test_circuit_breaker_opens_after_three_failures` — existing behaviour, must not regress.
5. All 15 existing orchestration tests pass.

### Manual verification (I run this)
```bash
docker compose exec orchestration python -c "
from app.services.supervisor import structured_llm
for q in ['What are the IELTS band requirements?',
          'Score my essay please',
          'Find me a masters in Germany',
          'How do I get a student visa?',
          'hello']:
    print(f'{q[:40]:42s} -> {structured_llm.invoke(q)}')
"
```
**Expect:** five lines, each showing a parsed `IntentResult` object with a sensible intent — **not** a raw string, **not** a validation error. If the output is a plain string, tool-use passthrough is broken and ag must tell me before proceeding.

### Definition of Done
- All 5 intents classify correctly across 3 consecutive runs.
- `with_structured_output` returns parsed objects.
- 15 existing tests pass; circuit breaker still opens after 3 failures.

---

## GOA-120 — RAG answer generation + Stage-3 boost

| | |
|---|---|
| **Service** RAG | **Priority** P1 | **Points** 1 | **Dependencies** GOA-117, GOA-118 |

**Files:** `services/rag/app/services/rag_service.py:32`, `services/rag/app/services/llm_boost.py:33–37`

> [!WARNING]
> **`llm_boost.py:34` currently targets `claude-3-haiku-20240307`, a deprecated model** (defect **D4**). This call site has almost certainly never succeeded against real Anthropic. Treat this as a **bug fix**, not a re-point — and be suspicious of any existing test claiming it passes, because it is presumably mocking the failure away.

### Steps
1. `rag_service.py:32` — `llm = ChatAnthropic(model=settings.llm_model, anthropic_api_key=..., ...base_url conditional...)`, same pattern as GOA-119 step 2.
2. `llm_boost.py:33–37` — replace `model_name="claude-3-haiku-20240307"` with the configured model. Note this site uses `model_name=` and `api_key=` (different kwarg names from `rag_service.py`) and reads the key via `os.getenv` rather than settings. **Move it onto `settings`** — leaving two config mechanisms in one service is how the next incident happens.
3. Keep `temperature=0.0` on the boost.
4. Keep the defensive clamp on the boost output (−10..+10). A frontier model is likelier to respect the range, but the clamp is correctness insurance, not a workaround.
5. Add `anthropic_base_url` and `llm_model` to `services/rag/app/core/config.py`.

### Automated tests (ag writes and runs these)
1. `test_query_returns_grounded_answer_with_sources` — assert the response cites at least one real document ID present in the DB.
2. `test_boost_is_clamped_to_range` — feed a mocked LLM returning `+999`, assert output is `+10`.
3. `test_boost_uses_configured_model` — assert `claude-3-haiku-20240307` appears nowhere in `services/rag/`.
4. `test_faq_short_circuit_skips_llm` — assert a known FAQ question issues **zero** LLM calls (spy on the client).
5. Existing RAG suite green.

### Manual verification (I run this)
**1. Grounded answer with real sources:**
```bash
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What are the requirements for a German student visa?"}' | jq
```
**Expect:** a substantive `answer` and a non-empty `sources` array. **An empty `sources` array means retrieval is broken** — likely embeddings (GOA-118), not the LLM.

**2. The boost actually runs (this is the deprecated-model fix):**
```bash
curl -s -X POST http://localhost:8000/score \
  -H 'Content-Type: application/json' \
  -d '{"userId":"<a real UUID from users>","programId":"11111111-1111-1111-1111-111111111111"}' | jq
```
**Expect:** a score object with a boost value **between −10 and +10**. If this errors on the model name, the fix did not land.

**3. `/match` still returns enriched entries:**
```bash
curl -s -X POST http://localhost:8000/match \
  -H 'Content-Type: application/json' \
  -d '{"userId":"<same UUID>"}' | jq '.programs | length'
```
**Expect:** a number **greater than 0**. `0` here is the exact symptom of the UUID-coercion bug fixed earlier — if it reappears, the regression is in `scoring.py`, not this ticket.

### Definition of Done
- `POST /query` returns grounded answers citing real sources.
- `POST /score` returns an in-range boost using a non-deprecated model.
- `POST /match` returns enriched entries.
- FAQ short-circuit still issues zero LLM calls.

---

## GOA-121 — Writing swarm

| | |
|---|---|
| **Service** Writing | **Priority** P1 | **Points** 1 | **Dependencies** GOA-117 |

**Files:** `services/writing/app/agents.py:358–362`, `services/writing/app/config.py:20–22, 39–42`

This is the **best-configured call site in the repo** — `writing_model` is already env-driven at `config.py:21/40` and the timeout at `:22/41`. The change is genuinely small.

### Steps
1. `config.py` — add `anthropic_base_url: str = ""` reading `os.getenv("ANTHROPIC_BASE_URL", "")`, matching the existing pattern at `:39–42`.
2. Change the `writing_model` default at `:21` and `:40` from `"claude-sonnet-4-6"` to `"claude-opus-4-8"`.
3. `agents.py:358–361` — add the conditional `base_url` kwarg to `AsyncAnthropic(...)`.
4. **Revert any timeout inflation.** `anthropic_timeout_seconds` is currently `25.0` (`config.py:22`) — the original cloud-era value, and correct. Do not raise it.
5. `api_key=settings.anthropic_api_key or "not-configured"` at `:359` exists to let tests construct the client. Keep it, but make sure it cannot mask a genuinely missing key at runtime: log a warning at startup if the key is the placeholder.

### Automated tests (ag writes and runs these)
1. `test_swarm_returns_four_criteria_plus_overall` — all four IELTS criteria and an overall band. Run 3×.
2. `test_sse_streams_per_criterion` — assert each criterion arrives as its own SSE event, not one terminal blob.
3. `test_timeout_is_25_seconds` — regression guard against re-inflation.
4. `test_placeholder_key_logs_warning` — construct with no key, assert the warning fires.
5. All **39** existing writing tests pass.

### Manual verification (I run this)
```bash
curl -N -X POST http://localhost:8001/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"task_type":"task2","essay":"Some people believe technology makes us more connected while others argue it isolates us. Discuss both views and give your opinion. In my view the evidence favours connection, though the picture is genuinely mixed..."}'
```
**Expect:** SSE events arriving **incrementally** — one per criterion (Task Response, Coherence & Cohesion, Lexical Resource, Grammatical Range & Accuracy) — then a final overall band. **All four arriving at once in a single blob means streaming is broken**, even though the content would look correct.

Then time it:
```bash
time curl -s -X POST http://localhost:8001/evaluate -H 'Content-Type: application/json' -d '{"task_type":"task2","essay":"..."}' > /dev/null
```
**Expect:** well under 25 s. If it approaches the timeout, the four agents are running serially rather than in parallel — tell me.

### Definition of Done
- 4 criteria + overall band, 3 consecutive runs.
- SSE streams per-criterion, incrementally.
- Timeout remains 25 s.
- 39 existing tests pass.

---

## GOA-122 — Speaking swarm (Go)

| | |
|---|---|
| **Service** Speaking | **Priority** P1 | **Points** 1 | **Dependencies** GOA-117 |

**Files:** `services/speaking/llm/client.go:28–34`, `services/speaking/cmd/speaking/main.go:52–53`, `docker-compose.yml:173–181`

> [!WARNING]
> **The speaking service currently has no `ANTHROPIC_API_KEY` in docker-compose at all** (defect **D2**). Its environment block sets only `PORT`, `MAX_CONNECTIONS`, `ELEVENLABS_API_KEY`, `OTEL_SERVICE_NAME`, and the three Langfuse vars. The Go client is being built from an empty string. **Fixing this is part of this ticket** — and it means the speaking LLM path has likely never worked in compose.

### Steps
1. `docker-compose.yml`, speaking `environment:` block — add:
   ```yaml
      - ANTHROPIC_AUTH_TOKEN=${ANTHROPIC_AUTH_TOKEN}
      - ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-}
      - LLM_MODEL=${LLM_MODEL:-claude-opus-4-8}
   ```
2. `llm/client.go:28` — widen the signature to accept a base URL:
   ```go
   func NewClient(model, apiKey, baseURL string) *Client {
       opts := []option.RequestOption{option.WithAPIKey(apiKey)}
       if baseURL != "" {
           opts = append(opts, option.WithBaseURL(baseURL))
       }
       c := anthropic.NewClient(opts...)
       return &Client{client: &c, model: model}
   }
   ```
   **If GOA-117's spike concluded Bearer**, swap `option.WithAPIKey` for `option.WithAuthToken`.
3. `cmd/speaking/main.go:52–53` — both call sites hardcode models:
   - `:52` practice → `llm.NewClient("claude-3-5-haiku-20241022", apiKey)`
   - `:53` exam → `llm.NewClient("claude-sonnet-4-6", apiKey)`

   Read both from env (`SPEAKING_PRACTICE_MODEL`, `SPEAKING_EXAM_MODEL`, both defaulting to `claude-opus-4-8`) and pass the base URL as the third argument. Keeping them as **two separate settings** matters — practice and exam have genuinely different cost/quality tradeoffs, which is what GOA-117 step 3 exists for.
4. **Do not raise the holistic timeout.** `internal/speaking/holistic_handler.go:45` is `15*time.Second` — the original cloud-era value, and it stands. The Ollama plan's raise is deleted.
5. Leave the other timeouts alone: `internal/speaking/client.go:257` (3500 ms swarm), `:332` (5 s), `:355` (10 s).

### Automated tests (ag writes and runs these)
1. `TestNewClientOmitsBaseURLWhenEmpty` — assert no `WithBaseURL` option is applied for `""`.
2. `TestNewClientAppliesBaseURLWhenSet` — assert it is applied for a non-empty value.
3. `TestHolisticReturnsFourCriteria` — full 4-criterion result within 15 s. Run 3×.
4. `TestHolisticDegradesGracefully` — with one agent failing, assert `partial: true` and no panic.
5. `TestHolisticTimeoutIsFifteenSeconds` — regression guard.
6. `go test ./...` fully green.

### Manual verification (I run this)
**1. The env vars actually reach the container** (this is the D2 fix):
```bash
docker compose up -d speaking && docker compose exec speaking env | grep -E 'ANTHROPIC|LLM_MODEL'
```
**Expect:** `ANTHROPIC_AUTH_TOKEN` non-empty, `ANTHROPIC_BASE_URL=https://agentrouter.org`, `LLM_MODEL=claude-opus-4-8`. **Before this ticket, this command returns nothing** — that is the bug.

**2. Holistic evaluation inside the original timeout:**
```bash
time curl -s -X POST http://localhost:8082/internal/evaluate/holistic \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"Well, I think living in a big city has many advantages. For example, there are more job opportunities and better public transport. However, the cost of living is much higher and it can feel quite isolating at times."}' | jq
```
**Expect:** all four criteria (Fluency & Coherence, Lexical Resource, Grammatical Range & Accuracy, Pronunciation) with band scores, `partial` absent or `false`, and a **wall time under 15 s**.

**3. Graceful degradation still works** — point the service at an unreachable base URL, restart it, and issue the same request.
**Expect:** `"partial": true` — **not** a 500, not a crashed container. Confirm with `docker compose ps speaking` that it is still `Up`.

### Definition of Done
- Speaking has Anthropic config in compose (D2 fixed).
- `POST /internal/evaluate/holistic` returns 4 criteria **within the original 15 s timeout**, 3 consecutive runs.
- `partial: true` degradation works.
- Both model names config-driven.
- `go test ./...` green.

---

## GOA-123 — Ingestion visa extraction

| | |
|---|---|
| **Service** Ingestion | **Priority** P2 | **Points** 1 | **Dependencies** GOA-117 |

**Files:** `services/ingestion/app/adapters/visa_adapter.py:29, 33, 116, 123–125, 202, 208–209, 225`

> [!NOTE]
> **Ingestion is not in docker-compose** (defect **D3**). Set env vars wherever the handler actually runs — Lambda config or local `.env`. Do not add it to compose as part of this ticket unless you also intend to own its lifecycle there.

### Steps
1. `:29` — `EXTRACTION_MODEL = "claude-haiku-4-5-20251001"` → `os.environ.get("EXTRACTION_MODEL", "claude-opus-4-8")`.
2. `:123–125` — add the conditional `base_url` to `AsyncAnthropic(...)`.
3. **Leave `MAX_TEXT_CHARS = 20000` at `:33` alone.** It is a cost control, not a context-window workaround. At $2/1M prompt tokens, 20 K chars ≈ 5 K tokens ≈ $0.01 per page — raising it raises cost linearly for marginal gain.
4. **Leave `max_tokens=2000` at `:209` and `timeout=30.0` at `:116` alone.** Both are original values.
5. `:225` records `"model": EXTRACTION_MODEL` in telemetry — this is the hook GOA-130 generalises. Make it also record `input_tokens` / `output_tokens` from `response.usage`.

**Why this ticket benefits most from the upgrade:** the extraction prompt carries four hard anti-hallucination constraints (null discipline, verbatim quoting for `extraction_evidence`, no inference, no cross-source merging). A frontier model holds these far better than a 3B. This is where the quality gain is most visible.

### Automated tests (ag writes and runs these)
1. `test_extraction_model_is_config_driven` — assert no hardcoded model literal remains.
2. `test_extraction_evidence_quotes_are_verbatim` — for a fixture page, assert every `extraction_evidence` string appears **literally** in the source text. This is the anti-hallucination guard and the most important test in the ticket.
3. `test_null_discipline` — for a page missing a field, assert `null` rather than a plausible invention.
4. `test_max_text_chars_truncation` — assert input is capped at 20,000 chars.
5. `test_usage_tokens_recorded_in_telemetry` — assert `input_tokens` and `output_tokens` are present.
6. All **19** existing visa adapter tests pass.

### Manual verification (I run this)
```bash
cd services/ingestion && python -c "
import asyncio, json
from app.adapters.visa_adapter import VisaAdapter
docs = asyncio.run(VisaAdapter().scrape())
print('sources processed:', len(docs))
for d in docs[:3]:
    print('---', d.get('url'))
    print(json.dumps(d, indent=2)[:800])
"
```
**Expect:** at least 3 sources processed, each with structured visa fields and an `extraction_evidence` array.

**Then the part that actually matters — spot-check one quote by hand.** Take any `extraction_evidence` string from the output, open that source URL in a browser, and Ctrl+F for it.
**Expect:** an exact match on the page. **If the quote is not literally on the page, the model is fabricating evidence and the ticket is not done** — no test-suite result overrides this check.

### Definition of Done
- A run over ≥3 sources completes.
- Model name config-driven; `MAX_TEXT_CHARS`, `max_tokens`, and `timeout` unchanged.
- Token usage recorded in telemetry.
- **Manually confirmed** that `extraction_evidence` quotes appear verbatim in the fetched pages.
- 19 existing tests pass.

---

## GOA-125 — Remove Stage-3 LLM boost from `/match` ranking

| | |
|---|---|
| **Service** RAG | **Priority** P2 | **Points** 1 | **Dependencies** GOA-120 |

**The rationale changed — this is now a cost fix, not a latency fix.** After GOA-115 brought the catalogue to ~50 programs, one `/match` becomes ~50 LLM calls ≈ **$0.05 per search, per user, uncached**. On a $150 quota that is 3,000 searches — plausible to burn in a single load test.

### Steps
1. In the `/match` path, rank on **Stage 1 (hard filters) + Stage 2 (deterministic scoring)** only.
2. **Keep the Stage-3 boost for single-program `/score`** — one call, high value, negligible cost.
3. Do not delete `llm_boost.py`. `/score` still uses it.
4. Verify the resulting ranking order against the pre-change order. If Stage-3 was meaningfully reordering results, removing it changes user-visible output — that is a product decision, not a refactor. **Tell me before shipping it.**

### Automated tests (ag writes and runs these)
1. `test_match_issues_zero_llm_calls` — spy on the Anthropic client, assert call count is exactly `0` for a `/match` request. **This is the whole ticket.**
2. `test_score_still_applies_boost` — assert `/score` still issues exactly one LLM call.
3. `test_match_ranking_order_unchanged` — snapshot the ordering before and after against a fixed fixture set.

### Manual verification (I run this)
```bash
docker compose logs -f rag &
curl -s -X POST http://localhost:8000/match -H 'Content-Type: application/json' -d '{"userId":"<real UUID>"}' | jq '.programs | length'
```
**Expect:** a non-zero program count, and **zero LLM request lines in the logs** during the call. Any outbound `agentrouter.org` traffic during `/match` means the boost is still wired in.

Then:
```bash
curl -s -X POST http://localhost:8000/score -H 'Content-Type: application/json' -d '{"userId":"<real UUID>","programId":"11111111-1111-1111-1111-111111111111"}' | jq
```
**Expect:** exactly **one** LLM call in the logs, and a boost value in the response.

### Definition of Done
- `/match` issues zero LLM calls.
- `/score` still applies the boost.
- Ranking order unchanged (or the change surfaced to me explicitly).

---

## GOA-129 — FAQ short-circuit: verify and expand

| | |
|---|---|
| **Service** RAG | **Priority** P2 | **Points** 1 | **Dependencies** GOA-120 |

**Was promoted to P1 under local inference; back to P2** now that a miss costs ~1 s and $0.007 rather than ~15 s. Still worth doing — free correctness and free money.

> [!IMPORTANT]
> **The core is already implemented.** `rag_service.py:45` has `_find_faq_match()`, `:42` sets `FAQ_SIMILARITY_THRESHOLD = 0.85`, and `:88` short-circuits before the LLM. **Do not re-implement it.** This ticket is coverage, calibration, and cleanup.

### Steps
1. **Expand coverage.** Migration `012_seed_egypt_faq_entries.sql` seeds ~6–8 Egypt entries against the 30 the original ticket specifies. Add `018_expand_faq_entries.sql` with the remainder. **Rollback goes in `migrations/rollback/`** — same rule as GOA-118.
2. **Calibrate the 0.85 threshold against real paraphrases.** For each seeded question, write 3 natural rewordings and measure the similarity score. If genuine paraphrases score 0.78–0.84, the threshold is too tight and is silently costing money on every near-miss. **Record the measured distribution** — do not just assert the constant.
3. **Delete the stale skip at `services/rag/tests/test_visa_integration.py:333`.** Its `reason` claims *"GOA-045 … is not implemented"* and *"there is no code path to exercise here yet"* — both now false — and its body is an empty `pass`. Replace it with a real test asserting the cache-hit path issues zero LLM calls.

### Automated tests (ag writes and runs these)
1. `test_exact_faq_question_short_circuits` — zero LLM calls, answer matches the seeded answer.
2. `test_paraphrased_faq_question_short_circuits` — 3 paraphrases per seeded question, all above threshold.
3. `test_unrelated_question_falls_through_to_llm` — asserts exactly one LLM call. **The guard against a threshold so loose it answers the wrong question.**
4. `test_threshold_boundary` — a question engineered to score just below 0.85 falls through; just above short-circuits.
5. `test_faq_seed_count` — assert the seeded row count meets the target.

### Manual verification (I run this)
**1. Coverage landed:**
```bash
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT count(*) FROM faq_entries;"
```
**Expect:** a count at or near 30, not 6.

**2. A cache hit is genuinely instant and free:**
```bash
docker compose logs --tail 0 -f rag &
time curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question":"<paste a seeded FAQ question verbatim>"}' | jq -r '.answer' | head -c 200
```
**Expect:** sub-second response, and **zero LLM traffic in the logs**.

**3. A paraphrase also hits** — repeat with my own rewording of the same question.
**Expect:** same behaviour. **If a natural paraphrase falls through to the LLM, the threshold is miscalibrated** — that is the actual finding this ticket exists to produce.

**4. An unrelated question does NOT hit:**
```bash
curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question":"What is the capital of Mongolia?"}' | jq -r '.answer'
```
**Expect:** a real LLM answer, **not** a seeded FAQ answer about visas. A false positive here is far worse than a miss.

### Definition of Done
- FAQ coverage at target.
- Threshold calibrated against measured paraphrase scores, with the distribution recorded.
- Stale skip at `test_visa_integration.py:333` deleted and replaced with a real test.
- No false-positive matches on unrelated questions.

---

## GOA-126 — Academic Task 1 chart extraction (vision)

| | |
|---|---|
| **Service** Writing | **Priority** P2 | **Points** 1 | **Dependencies** GOA-117, GOA-121 |

Claude Opus supports image input natively, so this reverts close to GOA-093's original intent: `claude-opus-4-8` with an image content block, **no local vision model, no model-swap juggling.**

### Step 0 — Spike multimodal passthrough (blocks the rest of the ticket)

`claude-opus-4-8` supports images, but whether a text-focused gateway **forwards image content blocks** is not guaranteed and is not documented.

```bash
docker compose exec writing python -c "
from anthropic import Anthropic
import os, base64
img = base64.b64encode(open('/app/tests/fixtures/test-chart.png','rb').read()).decode()
c = Anthropic(auth_token=os.environ['ANTHROPIC_AUTH_TOKEN'], base_url='https://agentrouter.org')
m = c.messages.create(model='claude-opus-4-8', max_tokens=100, messages=[{'role':'user','content':[
    {'type':'image','source':{'type':'base64','media_type':'image/png','data':img}},
    {'type':'text','text':'Describe this image in one sentence.'}]}])
print(m.content[0].text)
"
```

Use a chart image with a **distinctive, verifiable detail** — a specific number or an unusual label. A generic "a bar chart showing data over time" response can be produced without seeing the image at all.

**If it fails,** in order of preference:
- **(a)** Use the OpenAI-compatible endpoint (`/v1`) for this one call, if it passes images.
- **(b)** Reinstate a local vision model (`qwen3-vl:2b`, 1.9 GB) for this single path.
- **(c)** Degrade Academic Task 1 to the text-only General Training treatment and record it as a known limitation.

> [!CAUTION]
> **Do not let a broken vision path silently produce Task Achievement feedback about a chart the model never saw.** If vision does not work, the failure must be loud — the request errors, or the response is explicitly marked text-only. A confident-sounding band score for an unseen chart is the worst possible outcome and no test that mocks the model will catch it.

### Steps (after the spike passes)
1. Add the image content block to the `academic_task1` path only.
2. **The extraction output schema must not change** — the downstream 4-agent pipeline consumes it as-is.
3. `general_task1` and `task2` must skip vision entirely — no image block, no extra tokens.
4. Add an explicit guard: if `academic_task1` is requested without a stimulus image, fail with a clear error rather than silently evaluating text-only.

### Automated tests (ag writes and runs these)
1. `test_academic_task1_sends_image_block` — assert the outbound message contains an `image` content block.
2. `test_general_task1_sends_no_image_block` — assert it does not.
3. `test_task2_sends_no_image_block` — assert it does not.
4. `test_extraction_schema_unchanged` — snapshot-assert the output schema against the pre-change shape.
5. `test_academic_task1_without_image_raises` — the loud-failure guard.
6. `test_academic_task1_end_to_end` — real image, 3 consecutive runs.

### Manual verification (I run this)
Pick a chart with a specific readable value (e.g. "Germany peaks at 34% in 2019"), then:
```bash
curl -s -X POST http://localhost:8001/evaluate \
  -H 'Content-Type: application/json' \
  -d "{\"task_type\":\"academic_task1\",\"essay\":\"The chart shows...\",\"image_base64\":\"$(base64 -w0 mychart.png)\"}" | jq
```
**Expect:** feedback that references the **specific value I chose**. Generic chart language with no verifiable detail means the model is confabulating from the essay text, not reading the image — **that is a failure even though the response looks fine.**

### Definition of Done
- Spike result recorded in `docs/INFERENCE.md` (passed, or which fallback was taken).
- `academic_task1` completes with a real stimulus image, 3 consecutive runs, referencing verifiable image detail.
- Output schema unchanged.
- `general_task1` / `task2` skip vision.
- Missing-image case fails loudly.

---

## GOA-127 — Speech: local sidecar replacing ElevenLabs

| | |
|---|---|
| **Service** New `services/speech/` | **Priority** P2 | **Points** 2 | **Dependencies** none |

**Unchanged by the router.** AgentRouter provides no STT/TTS — those are not LLM products. This addresses blocker **B4**.

A CPU-only `services/speech/` sidecar wrapping `faster-whisper` (`small`, int8, ~1.5 GB RAM) and Piper replaces both legs.

**Still the cuttable ticket:** the exam speaking path takes text, so the 3-part exam → holistic evaluation demos fully without audio. If time runs short, cut this and demo the exam path.

### Steps
1. Create `services/speech/` with two endpoints: `POST /stt` (audio in, transcript out) and `POST /tts` (text in, audio out).
2. `faster-whisper` with `model_size="small"`, `compute_type="int8"`, `device="cpu"`. **Zero VRAM** — the GPU is not involved.
3. Piper for TTS with a single English voice.
4. Add to `docker-compose.yml` as a new service; add `SPEECH_SERVICE_URL` to the speaking service's environment. **Add it to `services/speaking`'s config AND its test config** — the two-places rule.
5. In the speaking service, wrap TTS calls so a sidecar failure yields `tts_unavailable` rather than a crash. The existing ElevenLabs client at `services/speaking/tts/client.go:22` is the seam.

### Automated tests (ag writes and runs these)
1. `test_stt_transcribes_fixture_wav` — a known WAV, assert the transcript contains expected keywords.
2. `test_tts_returns_playable_audio` — assert a valid audio container and non-trivial length.
3. `TestTTSUnavailableWhenSidecarDown` (Go) — kill the sidecar, assert `tts_unavailable`, no panic.
4. `test_stt_latency_recorded` — capture the measured latency; it feeds GOA-032's SLO restatement.

### Manual verification (I run this)
**1. STT works on my own voice:**
```bash
curl -s -X POST http://localhost:8085/stt -F 'audio=@myrecording.wav' | jq -r '.transcript'
```
**Expect:** a transcript I recognise as what I actually said. Record the wall time — STT is the slow leg and GOA-032's `<3 s` P95 depends on it.

**2. TTS produces audio I can hear:**
```bash
curl -s -X POST http://localhost:8085/tts -H 'Content-Type: application/json' \
  -d '{"text":"Describe a place you like to visit."}' --output out.wav && start out.wav
```
**Expect:** it plays, and it is intelligible.

**3. Full practice WebSocket round trip** — run a practice session end to end in the UI.
**Expect:** question audio plays, my answer transcribes, evaluation returns.

**4. Graceful failure:**
```bash
docker compose stop speech
# then start a practice session
```
**Expect:** `tts_unavailable` surfaced in the UI, speaking service still `Up`, no crash.

**5. Zero VRAM** — run `nvidia-smi` during a transcription.
**Expect:** no Python process holding GPU memory.

### Definition of Done
- `/stt` transcribes the fixture WAV **and my own recording**.
- `/tts` returns audio I can hear.
- Full practice WS round trip works.
- Sidecar uses zero VRAM (confirmed with `nvidia-smi`).
- Killing it mid-session yields `tts_unavailable`, not a crash.
- STT latency measured and recorded for GOA-032.

---

## GOA-130 — Budget instrumentation and guardrail

| | |
|---|---|
| **Service** Cross-service | **Priority** P2 | **Points** 1 | **Dependencies** GOA-117 |

$150 is finite and GOA-028's eval suite is specified to run on **every PR** at ~$1.50–2.00 per run. Twenty PRs is a quarter of the quota.

### Steps
1. **Generalise the existing telemetry.** `visa_adapter.py:225` already records `"model": EXTRACTION_MODEL`. Extract that pattern into a small shared helper recording `model`, `input_tokens`, `output_tokens` from `response.usage` at **every** call site in Part 1's table.
2. Compute spend against the published rates ($2 prompt / $10 completion per 1M). Put the rates in **config, not code** — they will change.
3. Expose through GOA-027's `GET /admin/costs`, which now returns **real** numbers instead of zeros.
4. Keep the GOA-020 path filter (`evals/**`, `services/**`) so evals do not fire on unrelated PRs.
5. Add a remaining-quota readout: total spend since a configured start, subtracted from a configured $150 budget.

### Automated tests (ag writes and runs these)
1. `test_usage_recorded_at_every_call_site` — parametrised over each service; assert token counts land in telemetry.
2. `test_cost_calculation_matches_published_rates` — 1M prompt + 1M completion → exactly $12.00.
3. `test_admin_costs_returns_nonzero_after_calls` — make a call, assert spend > 0.
4. `test_rates_are_config_driven` — assert `2.00` / `10.00` are not hardcoded in logic.

### Manual verification (I run this)
```bash
curl -s http://localhost:8080/admin/costs | jq
```
**Expect:** non-zero per-user spend. **Zero after I have made real calls means instrumentation missed a call site** — check which service is absent from the breakdown.

Then cross-check against the source of truth: compare the reported total against `$150 − remaining balance` in the AgentRouter console.
**Expect:** same ballpark. Order-of-magnitude agreement is enough; exact agreement is not expected (the gateway may bill differently).

Finally, measure one full eval run — note `/admin/costs` before, run the eval suite, note it after.
**Expect:** roughly $1.50–2.00. **If it is materially higher, tell me before enabling it on every PR** — that changes the budget arithmetic.

### Definition of Done
- `/admin/costs` returns non-zero per-user spend covering **all six** call sites.
- A full eval run's cost measured and recorded.
- Remaining quota checkable at a glance.
- Rates config-driven.

---

# PHASE 3 — Demo readiness

## GOA-124 — End-to-end verification and provider-switch runbook

| | |
|---|---|
| **Service** Cross-service | **Priority** P1 | **Points** 2 | **Dependencies** GOA-117 → GOA-130 |

### Steps
1. Walk all four journeys end to end, **recording timings**. Cloud-speed is back, so the demo script's pacing reverts to the original assumptions — but measure, do not assume.
2. Confirm the **text-based exam speaking path** works with zero audio dependency. This remains the safest demo path and the fallback if GOA-127 is cut.
3. Write `docs/INFERENCE.md` covering: AgentRouter setup, the **auth mechanism the GOA-117 spike settled**, model choice and rationale, the **GOA-126 vision spike result**, measured latencies per service, remaining quota, and the switch-back procedure.
4. Verify the switch-back: unset `ANTHROPIC_BASE_URL` with a direct Anthropic key present, confirm the system still works.
5. **Re-state which of blockers B1–B4 remain open** in the runbook, so the demo does not promise something that was never built.

### Automated tests (ag writes and runs these)
1. Full E2E suite across all four journeys against local docker-compose.
2. `test_provider_switchback` — with `ANTHROPIC_BASE_URL` unset, assert clients target the Anthropic default and a smoke call still works.
3. Every service suite green: orchestration, rag, writing, exam, user, gateway, ingestion, plus `go test ./...` for speaking and gateway.

### Manual verification (I run this)
**1. Cold start from scratch — the real test:**
```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 60
docker compose ps
```
**Expect:** every service `Up`. **Nothing `Restarting`, nothing `Exited`.** This project has had five separate crash-loops and four stale-image incidents; `--no-cache` and `down -v` are not paranoia, they are the lesson.

**2. Walk all four journeys in the UI myself**, stopwatch in hand. Record each duration in `docs/INFERENCE.md`.

**3. Switch-back drill:**
```bash
# comment out ANTHROPIC_BASE_URL in .env
docker compose up -d --force-recreate
curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"test"}' | jq -r '.answer'
```
**Expect:** with a direct Anthropic key it answers; without one it fails with a **clear auth error** — not a silent hang, not a fabricated answer.

**4. Quota check** — open the AgentRouter console.
**Expect:** remaining balance comfortably above zero with margin for the demo and rehearsals. **Check this the morning of the demo.**

### Definition of Done
- All four journeys pass from a cold `down -v` / `--no-cache` start.
- Every suite green.
- `docs/INFERENCE.md` usable by a second person on a cold machine.
- Switch-back verified.
- Open blockers restated honestly.

---

# Deleted from the Ollama plan

| Removed | Why |
|---|---|
| **LiteLLM proxy container** | AgentRouter is natively Anthropic-compatible — nothing to translate |
| **Ollama for LLM inference** | Replaced by `claude-opus-4-8`. Ollama survives only for `nomic-embed-text` |
| **`qwen2.5:3b-instruct`, `qwen3-vl:2b`, `llama3.2` A/B** | No longer needed |
| **GOA-128 — 5-laptop inference pool** | Request-parallelism across laptops solved a serialization problem that no longer exists. Keep as a "future work" note in the thesis if the distributed-inference analysis is worth writing up |
| **Ollama tuning** (`NUM_PARALLEL`, `MAX_LOADED_MODELS`, `KEEP_ALIVE`) | Irrelevant for a single 274 MB embedder |
| **`max_tokens` cuts and timeout inflation** | Frontier latency does not require them — every original value stands (writing 25 s, speaking 15 s, ingestion 30 s) |

---

# Downstream impact — Sprints 3 and 4

The Ollama plan forced several Sprint 3/4 compromises. **Most are now reversed.** Each affected ticket carries a `⚠️ ROUTER IMPACT` note in [GOA_Sprint_3_Tickets.md](GOA_Sprint_3_Tickets.md) and [GOA_Sprint_4_Tickets.md](GOA_Sprint_4_Tickets.md).

## Reversed — these work again

| Ticket | Restored |
|---|---|
| **GOA-028** | LLM-as-a-Judge is **meaningful again** — a frontier model judging frontier output is a real accuracy signal. The >80% ACCURATE target is back in play. Consider judging with a *different* model (`gpt-5.5`) to avoid the self-referential caveat. |
| **GOA-040** | Three of four blocked Gold Tier items return: judge accuracy, real cost figures, per-request cost on the Langfuse trace. Only the CloudWatch screenshot stays blocked (needs AWS). |
| **GOA-027** | `GET /admin/costs` returns **real non-zero spend** (GOA-130). Langfuse cost-per-request populates. |
| **GOA-046** | The `$1/user/day` AI-cost alert is meaningful again. |
| **GOA-066** | Grading-latency thresholds revert to the original 30 s. |
| **GOA-055–058** | Exam UI loading states revert to cloud-speed assumptions — no 60 s overlay redesign. |
| **GOA-036** | Load testing is compute-feasible again; the practical limit is **budget**, not GPU. Scope by spend, not concurrency ceiling. |

## Still constrained

| Ticket | Why |
|---|---|
| **GOA-032** | `<3 s` P95 remains **hard but no longer hopeless**. The LLM leg is fast again, but STT is a local CPU model (~3–8 s). Measure in GOA-127 before committing; the SLO may need restating for the STT leg specifically. |
| **GOA-021/022/031/037/041/044/073** | Blocked by **missing AWS credentials**, unrelated to inference. Unchanged. |
| **GOA-127-related speech criteria** | No STT/TTS on the router; the local sidecar stands. |

## Unchanged

**GOA-118's embedding migration**, **GOA-033's cross-encoder** (always local, never blocked), **GOA-045/129's FAQ short-circuit** (still free correctness, lower urgency).

## Not addressed anywhere in this plan

Blockers **B1** (Cambridge content), **B2** (CV Processor Lambda), **B3** (LocalStack resources) from Part 0. These need their own tickets, or an explicit decision to declare them known limitations.

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


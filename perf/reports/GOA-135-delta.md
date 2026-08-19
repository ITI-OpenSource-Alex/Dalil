# GOA-135 — pre/post delta

**Ticket:** GOA-135 — RAG: LLM client lifecycle, cost accounting, retry policy
**Harness:** `perf/llm_cost_bench.py` (one code path, run twice)
**Providers:** AgentRouter `https://agentrouter.org`, model `claude-opus-4-8`, `real: true`
**Artefacts:** `GOA-135-pre-20260805T061534Z.json` · `GOA-135-post-20260805T075516Z.json`

---

## C1 — cost accounting

Ratio is *reported ÷ true*, on a representative RAG call shape (2,000 prompt +
300 completion). True cost at $2.00 / $10.00 per 1M = **$0.007000**.

| Site | Pre ratio | Pre $ | Post ratio | Post $ | Target | ✅ |
|---|---|---|---|---|---|---|
| `rag/app/services/rag_service.py` | **0.125** (8× under) | 0.000875 | **1.000** | 0.007000 | 1.000 | ✅ |
| `writing/app/agents.py` | **1.500** (1.5× over) | 0.010500 | **1.000** | 0.007000 | 1.000 | ✅ |
| `writing/cv_processor/structured.py` | **0.500** (2× under) | 0.003500 | **1.000** | 0.007000 | 1.000 | ✅ |
| `ingestion/handler.py` | **4.000** (4× over) | 0.028000 | **1.000** | 0.007000 | 1.000 | ✅ |
| `gateway/config.go` (C1b, canonical) | 1.000 | 0.007000 | 1.000 | 0.007000 | unchanged | ✅ |

Each post row is corroborated by a source-level check, not only by arithmetic:
`imports_goa_pricing: true` and `old_literals_present: []` for all four. The
arithmetic alone could have been satisfied by a mirror that drifted from the code
it mirrors.

**The Gateway was already correct and was not touched.** Its `LLMPricingJSON`
default is the source the shared table now reads, and
`test_default_table_matches_gateway_exactly` parses the Go struct tag and asserts
the agreement rather than asking two files to stay in step by convention.

## C3 / C4 — client lifecycle

20 sequential calls per arm, same endpoint, same payload, back to back.

| Metric | Unpooled (pre shape) | Pooled (post) | Target | ✅ |
|---|---|---|---|---|
| TCP connections | **20** | **1** | ≤ 3 | ✅ |
| Latency p50 | 907.5 ms | **295.4 ms** | ≥ 30 ms faster | ✅ |
| Latency p95 | 963.4 ms | **331.4 ms** | — | ✅ |
| Latency min | 892.7 ms | **293.6 ms** | — | ✅ |

**p50 delta ≈ 612 ms.** The ticket predicted "≥ 30 ms, and it may not clear the
noise", with a warning not to manufacture a latency win. No manufacturing was
needed: the TLS handshake to `agentrouter.org` costs roughly **three times the
request itself**, and RAG was paying it on every query that reached the LLM. The
conservative target was wrong by a factor of twenty, in the project's favour.

## C7 — retry policy

A permanent 401, driven through the **shipped** `_invoke_llm_with_retry`
(`driver: rag_service._invoke_llm_with_retry`, not a lookalike in the harness).

| Metric | Pre | Post | Target | ✅ |
|---|---|---|---|---|
| Outbound requests | **2** | **1** | 1 | ✅ |
| Wall time | 1,223.6 ms | **945.7 ms** | roughly halves | ⚠️ see note |
| Log line | absent | `LLM invoke failed permanently (AuthenticationError), not retrying` | present | ✅ |

⚠️ Wall time fell 23%, not 50%. The second request was never a full round trip —
the first 401 arrives after connection setup, so the retry reuses a warm socket
and costs less than the first attempt. One request is the number that matters and
it is exact; the wall-time figure is reported as measured rather than rounded
toward the prediction.

---

## Tests — in-container, against freshly built images

All four images rebuilt (`docker compose build rag writing ingestion orchestration`,
exit 0) and every suite run inside its own container.

| Suite | Result |
|---|---|
| `services/rag/tests/` | **272 passed, 2 skipped, 0 failed** |
| `services/writing/tests/` | **83 passed, 3 skipped, 0 failed** |
| `services/ingestion/tests/` | **190 passed, 1 skipped, 0 failed** |
| `packages/pricing/py/tests/` (in the rag image) | **18 passed, 3 skipped** — the 3 gateway-parity tests skip correctly, the Go source is not mounted there |
| `services/orchestration/tests/` | 168 passed, **1 failed** — pre-existing, see below |
| `packages/pricing/py/tests/` (host) | **21 passed** |
| `services/rag/tests/test_llm_client.py` (host) | **25 passed** |

Every module that could not be collected on the host — 14 in RAG, 2 in writing —
runs and passes in-container. The 20 ingestion failures and 7 RAG
`Connection` failures seen on the host were all host-environment artefacts and do
not occur in the containers.

### The one remaining failure is not ours

`orchestration/tests/test_integration.py::test_langfuse_failure_does_not_block_chat`
fails on a latency assertion — `assert 3.185 < 1`, i.e. the chat path took 3.2s
against a 1s budget when Langfuse is unreachable.

Confirmed unrelated to this ticket:
- `git grep goa_pricing -- services/orchestration` returns **nothing**; the
  service does not use the shared table at all.
- Re-run with `PYTHONPATH` forced back to its pre-change value (`/opt/goa`):
  **fails identically**. The only change this ticket makes to orchestration is
  that `PYTHONPATH` entry and a Dockerfile `COPY`, neither of which can add 3s of
  latency.

### Host-side environment notes (for anyone reproducing)

These affect the host only and are documented so the next person does not chase them:
- **RAG:** 14 modules fail at collection with
  `ImportError: cannot import name 'get_client' from 'langfuse'` — a local
  virtualenv version mismatch of the same class `tests/conftest.py` already
  documents for aiobotocore. The container installs a matched pair.
- **Writing:** the two CV modules need `python-docx`, absent from the host venv.
- **Ingestion:** 20 host failures, count and identity unchanged with the change
  stashed.

**Run these suites in-container.** The host venv is shared across services and
does not represent any service's real dependency set.

---

## Packaging — a defect found during the container build

The first pass put `goa_pricing` in `/opt/goa`, alongside `goa_security`, and it
would have shipped an image where the package **exists and is invisible**.

`docker-compose.yml` bind-mounts `./packages/security/py:/opt/goa` for the dev
target of rag, writing, cv-processor and orchestration. A bind mount hides
whatever the image put at that path, so `COPY packages/pricing/py /opt/goa`
survives in the image and disappears the moment the service runs under compose —
the host-side tests would stay green, and every containerised service would fail
at import.

`services/rag/Dockerfile:22-25` already warned about exactly this shape for
`/app`, which is how it was spotted.

**Fixed:** the package gets its own root, `/opt/goa-pricing`, with its own mount
and its own `PYTHONPATH` entry, so image and compose agree.

| File | Change |
|---|---|
| `services/{rag,writing,orchestration}/Dockerfile` | `COPY packages/pricing/py /opt/goa-pricing`, `PYTHONPATH` extended |
| `services/ingestion/Dockerfile` | `COPY packages/pricing/py/goa_pricing ./goa_pricing` (this service vendors packages into `/app`, matching its `contracts` precedent) |
| `docker-compose.yml` | `./packages/pricing/py:/opt/goa-pricing` on all four services; `PYTHONPATH` extended where set in the environment block |
| `.github/workflows/ci.yml` | `PYTHONPATH` extended for both Python test steps |

---

## Scope note

The ticket as written covered RAG only. Its own acceptance criteria required a
cross-service pricing audit, and that audit found four wrong sites rather than
one — in **both** directions, which is why no aggregate had ever looked obviously
wrong. Fixing only RAG would have left three services wrong and made the audit
criterion a lie, so `writing`, `cv_processor` and `ingestion` were brought in.

The ticket's original claim that the wrong figures corrupt GOA-046's budget
alerting was **incorrect and has been corrected in the ticket**: `record_llm_cost`
records *tokens*, and the Gateway converts them with the correct table. The blast
radius is per-call `cost_usd` in Langfuse traces and the ingestion run summary.

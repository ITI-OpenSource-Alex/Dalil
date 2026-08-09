# GOA-135 — AgentRouter pricing refresh delta

**Scope:** urgent 2026-08-05 catalogue correction after the GOA-135 consolidation
**Harness:** `perf/llm_cost_bench.py`, run in the RAG container for both phases
**Artefacts:** `GOA-135-pricing-refresh-pre-20260805T192158Z.json` · `GOA-135-pricing-refresh-post-20260805T192528Z.json`

The benchmark uses fixed token counts and an independently supplied AgentRouter
catalogue, so no provider call is needed. The `providers.llm.real: false` marker
states that C3/C4/C7 were deliberately skipped; it does not weaken the exact C1
arithmetic measured here.

## Cost correction

Representative call: 2,000 prompt tokens + 300 completion tokens on
`claude-opus-4-8`. At the live $6/$30 rate the true cost is **$0.021000**.

| Site | PRE reported | PRE ratio | POST reported | POST ratio | Target | Verdict |
|---|---:|---:|---:|---:|---:|---|
| RAG | $0.007000 | 0.333 | $0.021000 | 1.000 | 1.000 | ✅ |
| Writing | $0.007000 | 0.333 | $0.021000 | 1.000 | 1.000 | ✅ |
| CV processor | $0.007000 | 0.333 | $0.021000 | 1.000 | 1.000 | ✅ |
| Ingestion | $0.007000 | 0.333 | $0.021000 | 1.000 | 1.000 | ✅ |
| Gateway | $0.007000 | 0.333 | $0.021000 | 1.000 | 1.000 | ✅ |

The PRE run confirms telemetry was exactly **3× low**. All Python callers inherit
the corrected shared table; the Gateway's independently parsed default now agrees.
The migration plan's representative 6,000/1,600-token swarm therefore moves from
about **$0.028 to $0.084**. A $150 quota buys roughly 1,786 such calls before
overhead (about 1,600 at the plan's original conservative rounding), not 5,000.

## Catalogue and fallback decision

| Model | Prompt / 1M | Completion / 1M | Status |
|---|---:|---:|---|
| `claude-opus-4-8` | $6 | $30 | current production model |
| `claude-opus-5` | $2 | $10 | live, added |
| `gpt-5.6-sol` | $6 | $36 | live, added |
| `claude-opus-4-6`, `claude-opus-4-7`, `glm-5.2`, `gpt-5.5` | — | — | delisted, removed |

`COST_PROMPT_PER_1M` / `COST_COMPLETION_PER_1M` now default to **$6/$30**.
That fallback deliberately matches the model currently deployed, rather than the
cheapest listed model or zero. The model itself was not switched, so GOA-133's
measurements remain valid.

## Configuration drift guard

The parity suite checks the Go and Python defaults plus `docker-compose.yml`, the
root `.env.example`, and `services/gateway/.env.example`. This matters because the
Compose value is injected at runtime and would otherwise override a corrected Go
default with stale prices.

## Verification

| Check | Result |
|---|---|
| Pricing package suite, in RAG container with full repository mounted | **24 passed** |
| Gateway Go suite, in Gateway container with Redis | **all packages passed** |
| RAG service suite, in container | **272 passed, 2 skipped** |
| Writing service suite, in container | **83 passed, 3 skipped** |
| Ingestion service suite, in container | **190 passed, 1 skipped** |
| Live `/admin/costs`, listed model, 2,000/300 tokens | expected $0.021 · actual **$0.021** |
| Live `/admin/costs`, unrecognized model fallback, 2,000/300 tokens | expected $0.021 · actual **$0.021** |
| Unknown model contract | `None`, never `0.0` |
| Provider-dependent GOA-135 latency/retry arms | skipped; outside pricing-refresh scope |

The first expanded RAG run caught `tests/test_llm_client.py` still asserting the
stale `$0.007` result. The assertion was updated to the corrected `$0.021` and the
entire suite was rerun to green. Infrastructure-only attempts made before
starting Postgres/Redis Cache are not counted as verification runs.

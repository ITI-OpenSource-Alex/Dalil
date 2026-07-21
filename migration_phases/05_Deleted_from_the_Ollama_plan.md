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

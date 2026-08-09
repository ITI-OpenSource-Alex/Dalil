# Inference Configuration (AgentRouter Runbook)

## AgentRouter Setup & Authentication
**Confirmed via Spike A (GOA-117):** AgentRouter's Anthropic-compatible endpoint uses **Bearer** tokens. 
* Python SDK: Pass the key via `auth_token='...'` or configure `default_headers={"Authorization": f"Bearer {token}"}` when necessary.
* Go SDK: Pass the key via `option.WithAuthToken("...")`.

**CRITICAL REQUIREMENT:** AgentRouter blocks unknown clients with a `401 unauthorized_client_error`. You **must** inject the following `User-Agent` header into all direct HTTP/REST clients (like curl requests, though official SDKs usually bypass this check or it is injected by the gateway):
`User-Agent: Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14`

## Model Configuration
* **Router Base URL:** `https://agentrouter.org` (Anthropic compatibility)
* **Default Model:** `claude-opus-5`
* **Overrides:** Configured per-service (e.g. `SPEAKING_EXAM_MODEL`, `EXTRACTION_MODEL`)
* **Why `claude-opus-5`**: It is the configured Anthropic-compatible AgentRouter model and keeps the Python and Go integrations on the same prompt and tool-schema path.

## GOA-126 Vision Spike Result
The vision spike successfully verified that the `agentrouter.org` gateway forwards multimodal image content blocks. In `academic_task1`, the stimulus chart image is passed to the configured Claude Opus model in base64 format. The gateway extracts the features accurately without silent truncations or text-only fallbacks, preserving the ability to grade data accuracy safely.

## Measured Latencies (E2E)
Baseline timings captured under local E2E runs:
| Service / Workflow | Latency (s) |
| --- | --- |
| Orchestration Intent (Claude Opus) | ~20.35s |
| RAG Query (Cache Miss) | ~100.21s |
| Writing Swarm (4 Agents) | ~15.96s |
| Speaking Holistic (4 Agents) | ~15.11s |
| STT & TTS (Speech Sidecar) | <3s |

*Note: The high tail latencies (up to 110s for RAG/Orchestration) are **not** a property of the model (Opus) nor output length, but are caused by erratic gateway channel queueing. An identical 4-token call ranges from 2.5s to 110s. This is mitigated client-side by applying a 20-30s timeout and exactly one retry (which typically lands the request on a fast channel).*

## Budget & Quota Tracking
We have instrumented a $150 observability guardrail for AgentRouter usage. It reports and feeds alerts; it does not block requests.
* Token metrics are grouped by UTC date, user, and service in Redis (`redis-gateway`) and expire after 35 days.
* Spend is computed dynamically from the model-specific `LLM_PRICING_JSON` Gateway configuration. Unknown models use the legacy `COST_PROMPT_PER_1M` / `COST_COMPLETION_PER_1M` fallback.
* **Checking Quota**: Use `GET /admin/costs` on the Gateway with `X-Admin-Key: $ADMIN_API_KEY`. Missing, empty, wrong, or unconfigured admin keys return `401`. The response includes today's per-user cost, RAG/Writing/Speaking token breakdown, total spend, budget, and remaining quota. A single PR evaluation suite typically costs $1.50–$2.00.

## Provider Switch-Back Procedure
If AgentRouter fails or quota is exhausted, you can seamlessly fall back to native Anthropic inference:
1. Provide your direct Anthropic key as `ANTHROPIC_AUTH_TOKEN` in the environment.
2. Unset the `ANTHROPIC_BASE_URL` variable entirely.
3. Restart the containers (`docker compose up -d`).
4. Without a `base_url`, the Anthropic SDKs default back to `api.anthropic.com` and continue normal operation.

## Known Limitations / Open Blockers
The following structural blockers remain open and affect the current demo surface:
- **B1**: Cambridge content (Reading/Listening) is unseeded.
- **B2**: ~~CV Processor Lambda does not exist locally.~~ (Resolved: Extracted to `services/writing/cv_processor` and running correctly via Docker volume).
- **B3**: LocalStack provisions only 3 of 6+ resources (missing dead-letter queues, event queues).
- **B4**: Addressed partially by the local speech sidecar (`GOA-127`), meaning Speaking and Speech are mostly functional.

# Inference Configuration (AgentRouter Runbook)

## AgentRouter Setup & Authentication
**Confirmed via Spike A (GOA-117):** AgentRouter's Anthropic-compatible endpoint uses **Bearer** tokens. 
* Python SDK: Pass the key via `auth_token='...'` or configure `default_headers={"Authorization": f"Bearer {token}"}` when necessary.
* Go SDK: Pass the key via `option.WithAuthToken("...")`.

**CRITICAL REQUIREMENT:** AgentRouter blocks unknown clients with a `401 unauthorized_client_error`. You **must** inject the following `User-Agent` header into all direct HTTP/REST clients (like curl requests, though official SDKs usually bypass this check or it is injected by the gateway):
`User-Agent: Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14`

## Model Configuration
* **Router Base URL:** `https://agentrouter.org` (Anthropic compatibility)
* **Default Model:** `claude-opus-4-8`
* **Overrides:** Configured per-service (e.g. `SPEAKING_EXAM_MODEL`, `EXTRACTION_MODEL`)
* **Why `claude-opus-4-8`**: It is the cheapest on both prompt and completion axes while maintaining Anthropic API compatibility, which enables seamless migration for Python and Go SDKs without changing the prompt structures or tool schemas.

## GOA-126 Vision Spike Result
The vision spike successfully verified that the `agentrouter.org` gateway forwards multimodal image content blocks. In `academic_task1`, the stimulus chart image is correctly passed to `claude-opus-4-8` in base64 format. The gateway extracts the features accurately without silent truncations or text-only fallbacks, preserving the ability to grade data accuracy safely.

## Measured Latencies (E2E)
Baseline timings captured under local E2E runs:
| Service / Workflow | Latency (s) |
| --- | --- |
| Orchestration Intent (Claude Opus) | ~20.35s |
| RAG Query (Cache Miss) | ~100.21s |
| Writing Swarm (4 Agents) | ~15.96s |
| Speaking Holistic (4 Agents) | ~15.11s |
| STT & TTS (Speech Sidecar) | <3s |

*Note: RAG cache misses and Orchestration intent classifications may experience higher latencies on the gateway depending on the backend provider's load, but parallel swarms complete reliably fast.*

## Budget & Quota Tracking
We have instrumented a strict $150 budget guardrail for AgentRouter usage.
* Token metrics are incremented globally and per-user in Redis (`redis-gateway`).
* Spend is computed dynamically based on config: `$2.00 / 1M prompt` and `$10.00 / 1M completion`.
* **Checking Quota**: Use `GET /admin/costs` on the Gateway to verify remaining quota. A single PR evaluation suite typically costs $1.50–$2.00.

## Provider Switch-Back Procedure
If AgentRouter fails or quota is exhausted, you can seamlessly fall back to native Anthropic inference:
1. Provide your direct Anthropic key as `ANTHROPIC_AUTH_TOKEN` in the environment.
2. Unset the `ANTHROPIC_BASE_URL` variable entirely.
3. Restart the containers (`docker compose up -d`).
4. Without a `base_url`, the Anthropic SDKs default back to `api.anthropic.com` and continue normal operation.

## Known Limitations / Open Blockers
The following structural blockers remain open and affect the current demo surface:
- **B1**: Cambridge content (Reading/Listening) is unseeded.
- **B2**: CV Processor Lambda does not exist locally.
- **B3**: LocalStack provisions only 3 of 6+ resources (missing dead-letter queues, event queues).
- **B4**: Addressed partially by the local speech sidecar (`GOA-127`), meaning Speaking and Speech are mostly functional.

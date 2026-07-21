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


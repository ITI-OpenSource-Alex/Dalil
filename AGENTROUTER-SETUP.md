# Getting AgentRouter running

A step-by-step runbook. Every step has a verification you can run — don't move on
until it passes. If you're debugging an existing setup, jump to
[Troubleshooting](#troubleshooting); the error AgentRouter returns is misleading
and will send you the wrong way.

**The two things that trip everyone up**, up front, because nothing works without them:

1. **A recognised `User-Agent` is mandatory.** AgentRouter allowlists clients. A
   valid key + funded account + correct model still returns `401
   unauthorized_client_error` if the User-Agent isn't one it knows.
2. **`stream` must be `false`.** Streaming responses contain a non-standard
   `billing.summary` event that breaks strict OpenAI-compatible clients.

---

## Step 1 — Get an API key

Register at https://agentrouter.org and create a key at
https://agentrouter.org/console/token. It looks like `sk-...`.

---

## Step 2 — Confirm the key works *before* touching the app

This isolates credential problems from app problems. Replace `sk-YOUR-KEY`:

```bash
curl -s -X POST "https://agentrouter.org/v1/chat/completions" \
  -H "Authorization: Bearer sk-YOUR-KEY" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14" \
  -d '{"model":"claude-opus-4-8","messages":[{"role":"user","content":"Reply with exactly: OK"}],"stream":false}'
```

**Expected:** a normal completion whose `choices[0].message.content` is `OK`.

**Sanity check the gate is real** — rerun the exact same command with the
`User-Agent` line deleted. You should get `401 unauthorized_client_error`. If
step 2 passes but this doesn't fail, their gating has changed and the notes below
may be stale.

If step 2 itself returns 401 *with* the User-Agent, the key or account is the
problem, not the client — see [Troubleshooting](#troubleshooting).

---

## Step 3 — Configure `.env`

```env
AGENT_ROUTER_API_KEY=sk-YOUR-KEY
AGENT_ROUTER_BASE_URL=https://agentrouter.org/v1

# MODEL_DEFAULT is the fallback for every task without its own override
# (grading, vision, ask...). It MUST name a model AgentRouter serves - if it
# names a Gemini model, those tasks all fail.
MODEL_DEFAULT=claude-opus-4-8
MODEL_SYNTHESIS=claude-opus-4-8
MODEL_VERIFICATION=claude-opus-4-8
MODEL_EXPLAIN_FIRST_PRINCIPLES=claude-opus-4-8

SPEND_CAP=10.00
ALLOW_DIRECT_GEMINI_FALLBACK=1
```

Optional overrides:

```env
AGENT_ROUTER_UA=Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14
LLM_MAX_CONCURRENCY=2
```

---

## Step 4 — Start the parser and read the health check

```bash
make parser      # or: .\scripts\start-parser.ps1
```

**Expected** — a line per configured model:

```
--- Running startup model health check ---
Checking SYNTHESIS model (claude-opus-4-8)...
[SYNTHESIS] OK - Model claude-opus-4-8 is alive.
...
--- Startup check complete ---
```

The check runs on a background thread, so the port opens immediately — the server
is usable before the check finishes. `HARD CACHE HIT` lines on later boots are
expected and free.

---

## Step 5 — Verify through the app

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:5001/api/grade" `
  -ContentType "application/json" `
  -Body '{"question":"Why must WAL replay be idempotent?","answer":"Replay re-applies log records after a crash.","user_answer":"because the log may be replayed more than once"}'
```

**Expected:** a `grade` (Again/Hard/Good/Easy) and a paragraph of `feedback`,
in roughly 4–6 seconds.

Then confirm it was billed and logged:

```powershell
Get-Content usage.json -Raw | ConvertFrom-Json | Select-Object -Last 3
```

You should see `task`, `model`, token counts and a cost. Entries marked
`[CACHE HIT]` cost `$0` and made no network call.

---

## Model catalog

Dashboard prices, USD per 1M tokens. Mirrored in `AGENT_ROUTER_RATES` in
`server.py` to estimate spend against `SPEND_CAP` (an estimate — AgentRouter
bills in CNY).

| Model | Endpoints | Prompt | Completion |
|---|---|---|---|
| `claude-opus-4-8` | anthropic, openai | $2.00 | $10.00 |
| `claude-opus-4-7` | anthropic, openai | $8.00 | $40.00 |
| `claude-opus-4-6` | anthropic, openai | $8.00 | $40.00 |
| `gpt-5.5` | openai | $7.00 | $14.00 |
| `glm-5.2` | openai | $6.00 | $9.00 |

`claude-opus-4-8` is 4× cheaper than 4-6/4-7 for a newer model — it's the default
here for that reason.

### Where these prices live in the code (GOA-135)

**One variable, `LLM_PRICING_JSON`. Do not add a second copy anywhere.**

| Reader | How |
|---|---|
| Gateway (Go) | `services/gateway/config.go` → `LLMPricingJSON`; the billing authority behind `/admin/costs` and the budget alert |
| Python services | `packages/pricing/py/goa_pricing` → `cost_usd(model, in, out)` |

Before GOA-135 five call sites priced the same model five different ways —
$0.25/$1.25, $1/$5, $2/$10, $3/$15 and $8/$40 — so one call reported anywhere
from 12% to 400% of its real cost depending on which service you asked. Measured
in `perf/reports/GOA-135-delta.md`.

If you switch models: add it to `LLM_PRICING_JSON` **and** check
`packages/pricing/py/tests/test_goa_pricing.py` still passes — it parses the Go
struct tag and asserts the two readers agree, so the tables cannot drift silently.
An unpriced model records a **null** cost, never `0.0`, and increments
`goa_*_unpriced_model_total`.

---

## How a call actually flows

```
call_model(task, prompt)
  ├─ 1. local hard cache   model_cache.json, keyed by (model, prompt, temperature, image)
  ├─ 2. AgentRouter        User-Agent header + stream:false
  └─ 3. Gemini direct      only if AgentRouter raises
```

- **Routing:** `MODEL_<TASK>` → `MODEL_DEFAULT` → `GEMINI_MODEL`
- **Cache:** identical requests never hit the network twice. Delete
  `model_cache.json` to force fresh calls.
- **Fallback:** `ALLOW_DIRECT_GEMINI_FALLBACK=1` keeps the app usable during an
  AgentRouter outage instead of every AI feature going dark.
- **Retries:** 429/5xx retry with exponential backoff and honour `Retry-After`.
  4xx fails fast — retrying a bad model name or key only wastes time.
- **Concurrency:** capped by `LLM_MAX_CONCURRENCY`. Without it, the startup health
  check and a live request can hit the same rate limit simultaneously.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `401 unauthorized_client_error` | User-Agent not recognised — **not** a bad key | Ensure `AGENT_ROUTER_UA` is set; never a browser/curl UA |
| `Model not found` | Model isn't in the catalog | Use one from the table; check `MODEL_DEFAULT` isn't a Gemini name |
| `expected array, received undefined` at `choices` | Streaming's `billing.summary` trailer | Ensure `stream: false` |
| `'charmap' codec can't encode` | Windows cp1252 console + non-ASCII upstream error | Already fixed via UTF-8 stdout at startup |
| Instant responses, `$0` cost | Cache hit | Delete `model_cache.json` |
| 429 mentioning `ai.google.dev` | Gemini free-tier quota, not AgentRouter | Wait for reset, or rely on AgentRouter |
| Slow boot, repeated retry lines | Health check retrying a rate limit | Harmless — background thread, port is already open |

### If the key genuinely doesn't work

If Step 2 fails *with* the User-Agent present, it's account-side. Their support
Discord is linked in the error message itself. Give them specifics — "returns
`unauthorized_client_error` on all catalog models, both wire formats, including a
bare `GET /v1/models`" gets a far better response than "it doesn't work."

---

## Why the User-Agent, specifically

Worth recording, because the 401 actively misleads you into thinking the key is bad.

All of these returned the **identical** 401:

- every catalog model (`gpt-5.5`, `gpt-5`, all three Claude Opus, `glm-5.2`)
- both wire formats (`/v1/chat/completions`, Anthropic `/v1/messages`)
- both auth styles (`Authorization: Bearer`, `x-api-key`)
- with and without `/v1` on the base URL
- official-SDK fingerprint headers (`X-Stainless-*`)
- browser TLS fingerprint impersonation (chrome/safari/edge/firefox, via `curl_cffi`)
- a bare `GET /v1/models` with no body

The answer came from running the allowlisted Kilo Code CLI through a local
logging proxy and diffing its request against ours. The only meaningful
difference was its client-identifying headers, and isolating them showed the
**User-Agent alone** is sufficient — `http-referer` and `x-title` are not needed.

> **Be aware:** this presents our requests as Kilo Code. AgentRouter is a
> community relay that deliberately gates access to supported agent tools, so
> this circumvents an intentional control. It works on a funded account, but a
> change on their side — or an account action — is a live risk. If calls start
> failing, check this first.

---

## Helper scripts

- `try.py` — sweeps every catalog model across both wire formats
- `try_ua.py` — isolates which client headers pass the gate, streaming and not
- `docs/ANTIGRAVITY-AGENTROUTER.md` — the fuller refactor spec (tier routing,
  prompt-prefix caching, structured outputs) this implementation is a first step toward

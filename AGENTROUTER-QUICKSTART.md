# AgentRouter quickstart for another project

This is the shortest known-good path for testing and integrating AgentRouter
without involving any GOA service. Start with the isolated request. Only add an
SDK or application framework after that request returns `OK`.

## 1. Configuration

Create a local `.env` file and do not commit it:

```env
AGENT_ROUTER_API_KEY=sk-your-key
AGENT_ROUTER_BASE_URL=https://agentrouter.org/v1
AGENT_ROUTER_MODEL=claude-opus-5
AGENT_ROUTER_UA=Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14
```

The current AgentRouter behavior has two compatibility requirements:

- Send a client `User-Agent` accepted by AgentRouter. An otherwise valid key can
  receive `401 unauthorized_client_error` when the header is missing.
- Set `stream` to `false`. Its streaming response may contain a non-standard
  billing trailer that strict OpenAI-compatible parsers reject.

The `AGENT_ROUTER_UA` value above is the compatibility header used by this
repository's provisioned AgentRouter integration. Keep it centralized because
it can change independently of application code.

## 2. Test the provider by itself

From this repository:

```powershell
py -3.11 scripts/smoke_agentrouter.py --timeout 30
```

The script reads `.env`, makes one direct OpenAI-compatible request, enforces a
hard total deadline, and never prints the key. A healthy result looks like:

```json
{"ok":true,"status":200,"latency_ms":2756.2,"content":"OK"}
```

Copy [scripts/smoke_agentrouter.py](scripts/smoke_agentrouter.py) into another
Python project if you want the same dependency-free diagnostic there. Rename
its environment variables if necessary; the wire request itself is generic.

## 3. Minimal Python integration

Install the OpenAI-compatible client:

```powershell
py -m pip install openai python-dotenv
```

```python
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["AGENT_ROUTER_API_KEY"],
    base_url=os.getenv("AGENT_ROUTER_BASE_URL", "https://agentrouter.org/v1"),
    default_headers={"User-Agent": os.environ["AGENT_ROUTER_UA"]},
    timeout=30.0,
    max_retries=0,
)

response = client.chat.completions.create(
    model=os.getenv("AGENT_ROUTER_MODEL", "claude-opus-5"),
    messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    max_tokens=16,
    temperature=0,
    stream=False,
)

print(response.choices[0].message.content)
```

Keep `max_retries=0` until a single call is proven. Afterward, add at most one
retry for timeouts, 429s, and 5xx responses. Do not retry 4xx responses: a bad
key, blocked client identity, or unknown model will fail the same way again.

## 4. Minimal Node.js integration

This example uses Node 20+ `fetch` and no SDK:

```javascript
const controller = new AbortController();
const timer = setTimeout(() => controller.abort(), 30_000);

try {
  const response = await fetch(
    `${process.env.AGENT_ROUTER_BASE_URL ?? "https://agentrouter.org/v1"}/chat/completions`,
    {
      method: "POST",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${process.env.AGENT_ROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "User-Agent": process.env.AGENT_ROUTER_UA,
      },
      body: JSON.stringify({
        model: process.env.AGENT_ROUTER_MODEL ?? "claude-opus-5",
        messages: [{ role: "user", content: "Reply with exactly: OK" }],
        max_tokens: 16,
        temperature: 0,
        stream: false,
      }),
    },
  );

  const payload = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(payload.error ?? payload));
  console.log(payload.choices[0].message.content);
} finally {
  clearTimeout(timer);
}
```

## 5. Production wrapper

Put provider details behind one function rather than spreading environment
lookups throughout the application. That wrapper should own:

- the base URL, token, model, and allowed `User-Agent`;
- a connection-pooled client reused for the life of the process;
- `stream: false` until AgentRouter's stream is parsed deliberately;
- a 20–30 second hard request deadline;
- at most one retry for a timeout, 429, or 5xx;
- sanitized logs containing status, latency, request ID, model, and token usage,
  but never the authorization header or prompt contents;
- a circuit breaker so an outage does not queue every application request;
- a fallback provider only when you explicitly accept its cost and behavior.

A timed-out generation may still complete and be billed upstream. Retrying can
therefore improve latency while producing two billed calls. Retry only
idempotent inference requests and track the tradeoff.

## 6. Error map

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| `401 unauthorized_client_error` | Client identity rejected | `User-Agent`, key, funded account |
| `401` from `api.anthropic.com` | Router key sent to the native provider | Base URL actually loaded by the process |
| Model/channel unavailable | Unsupported model | Use a model shown in the AgentRouter account catalog |
| Missing `choices` / billing event parse error | Non-standard stream trailer | Send `stream: false` |
| Fast isolated call, slow application | App critical path | Classification calls, retrieval, telemetry, proxy buffering |
| Isolated call varies from seconds to minutes | Router/provider channel queueing | Hard timeout, one bounded retry, circuit breaker |
| `429` | Rate or account quota | Reduce concurrency; honor `Retry-After` |

## 7. Debugging order

1. Run the isolated smoke script.
2. Log the resolved host, model, timeout, and presence—not value—of the token.
3. Test the exact same prompt through your provider wrapper.
4. Test the application's endpoint with every database/tool call mocked.
5. Re-enable retrieval, tools, telemetry, and retries one at a time.
6. Compare time-to-first-byte and total time. A UI cannot fix a slow first byte;
   it can only show honest progress while waiting.

For GOA-specific Compose settings and service-by-service notes, see
[AGENTROUTER-SETUP.md](AGENTROUTER-SETUP.md) and
[docs/INFERENCE.md](docs/INFERENCE.md).

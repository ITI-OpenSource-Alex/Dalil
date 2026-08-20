# AgentRouter implementation handoff

This project owner authorizes using the project's provisioned AgentRouter
account for application inference. The repository contains a valid funded key
in the uncommitted `.env`, and an isolated call was verified successfully on
2026-08-20:

```text
HTTP 200
model: anthropic/claude-opus-5-ps-aws-dst
response: OK
latency: 2.76 seconds
tokens: 20 total
```

Use these settings:

```env
AGENT_ROUTER_BASE_URL=https://agentrouter.org/v1
AGENT_ROUTER_MODEL=claude-opus-5
AGENT_ROUTER_UA=Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14
```

Read the token from `AGENT_ROUTER_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or the
project's equivalent secret variable. Never print or commit it.

The `User-Agent` above is a required compatibility header for this configured
integration. It is part of the known-good client configuration, alongside the
base URL and model. Send OpenAI-compatible requests to
`/v1/chat/completions` with Bearer authentication and `stream: false`.

Before integrating with the application, run:

```powershell
py -3.11 scripts/smoke_agentrouter.py --timeout 30
```

Then implement the provider behind one reusable client with connection pooling,
a 30-second hard timeout, no automatic 4xx retries, and at most one retry for
timeouts, 429s, or 5xx responses. AgentRouter calls are authorized by the user;
proceed with the integration and report concrete HTTP errors if one occurs.

Full code examples are in [AGENTROUTER-QUICKSTART.md](AGENTROUTER-QUICKSTART.md).

# PHASE 3 — Demo readiness

## GOA-124 — End-to-end verification and provider-switch runbook

| | |
|---|---|
| **Service** Cross-service | **Priority** P1 | **Points** 2 | **Dependencies** GOA-117 → GOA-130 |

### Steps
1. Walk all four journeys end to end, **recording timings**. Cloud-speed is back, so the demo script's pacing reverts to the original assumptions — but measure, do not assume.
2. Confirm the **text-based exam speaking path** works with zero audio dependency. This remains the safest demo path and the fallback if GOA-127 is cut.
3. Write `docs/INFERENCE.md` covering: AgentRouter setup, the **auth mechanism the GOA-117 spike settled**, model choice and rationale, the **GOA-126 vision spike result**, measured latencies per service, remaining quota, and the switch-back procedure.
4. Verify the switch-back: unset `ANTHROPIC_BASE_URL` with a direct Anthropic key present, confirm the system still works.
5. **Re-state which of blockers B1–B4 remain open** in the runbook, so the demo does not promise something that was never built.

### Automated tests (ag writes and runs these)
1. Full E2E suite across all four journeys against local docker-compose.
2. `test_provider_switchback` — with `ANTHROPIC_BASE_URL` unset, assert clients target the Anthropic default and a smoke call still works.
3. Every service suite green: orchestration, rag, writing, exam, user, gateway, ingestion, plus `go test ./...` for speaking and gateway.

### Manual verification (I run this)
**1. Cold start from scratch — the real test:**
```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 60
docker compose ps
```
**Expect:** every service `Up`. **Nothing `Restarting`, nothing `Exited`.** This project has had five separate crash-loops and four stale-image incidents; `--no-cache` and `down -v` are not paranoia, they are the lesson.

**2. Walk all four journeys in the UI myself**, stopwatch in hand. Record each duration in `docs/INFERENCE.md`.

**3. Switch-back drill:**
```bash
# comment out ANTHROPIC_BASE_URL in .env
docker compose up -d --force-recreate
curl -s -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"test"}' | jq -r '.answer'
```
**Expect:** with a direct Anthropic key it answers; without one it fails with a **clear auth error** — not a silent hang, not a fabricated answer.

**4. Quota check** — open the AgentRouter console.
**Expect:** remaining balance comfortably above zero with margin for the demo and rehearsals. **Check this the morning of the demo.**

### Definition of Done
- All four journeys pass from a cold `down -v` / `--no-cache` start.
- Every suite green.
- `docs/INFERENCE.md` usable by a second person on a cold machine.
- Switch-back verified.
- Open blockers restated honestly.

---


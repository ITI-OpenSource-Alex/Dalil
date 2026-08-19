# GOA-036 — top 3 bottlenecks

From run `20260811T032552Z`. Every figure is measured; supporting artefacts are
named per finding.

---

## 1. Per-feature rate limits, not capacity, set the system's throughput ceiling

**Severity: highest.** It is the reason no other bottleneck could be measured.

### Evidence

`20260811T032552Z-k6.json` and `GOA-036-prometheus-window.txt`:

| Endpoint | Attempted | Refused 429 | Completed |
|---|---|---|---|
| `POST /api/opportunities/query` | ~2,936 | **2,475 (84%)** | ~461 |
| `POST /api/writing/essays/{id}/evaluate` | 115 | **~110 (96%)** | ~5 |
| `POST /api/chat` | 181 | 0 | 181 (approaching its 200/hr ceiling) |

Total 429s across the run: **2,585 of 3,342 requests (77%)**.

Configured in `services/gateway/config.go`:

```go
ChatQueriesPerHour         default:"20"
OpportunitySearchesPerHour default:"20"
EssayEvalsPerHour          default:"5"
CVReviewsPerHour           default:"5"
```

plus a global `/api` limiter of 60 requests per user per minute
(`server.go:172`).

### Why it matters

These are per-user hourly ceilings, and they are low enough that a **single
engaged user** hits them in ordinary use: 20 chat questions or 5 essay
evaluations is under an hour of genuine study. A user preparing for an exam will
be refused, and the UI has no vocabulary for "come back in an hour".

They also make the system unmeasurable. 77% of this load test was refused, so no
capacity limit, queueing behaviour or saturation point was reached. Any future
performance work is blind until this is separable.

### What to do

1. **Decide whether these numbers are the product's intent.** They read as cost
   control, and cost control at 5 essay evaluations per hour is a product
   decision that should be explicit rather than a default in a config struct.
2. **Make them overridable for load testing**, so a run can measure the system
   rather than the limiter. They are already `envconfig`; compose does not pass
   most of them.
3. **Surface the limit to the user.** A 429 today is an opaque failure. It
   should say what was exhausted and when it resets.

---

## 2. Chat P95 is 59.9 seconds against a 5-second target

**Severity: high.** The single crossed threshold, and the most user-visible one.

### Evidence

| | ms |
|---|---|
| P50 | 26,923 |
| P90 | 47,916 |
| **P95** | **59,885** |
| Max | 99,896 |

Ticket criterion: P95 < 5,000. Measured **12× over**. The threshold was left at
the ticket's value rather than widened, so k6 exits 99.

Corroborating: `http_req_waiting` P95 = 4,322ms while `http_req_duration` P95 =
9,695ms across all endpoints — the time is not spent waiting for the first byte,
it is spent streaming the SSE response while the model generates.

### Composition

A chat turn is: Gateway JWT + limiter → orchestration → RAG retrieval (embedding
via host Ollama, then pgvector ANN) → LLM generation via AgentRouter → SSE
stream back. RAG retrieval alone measured **p50 1,805ms / p95 2,150ms**
(`GOA-030-probes-sweep.json`), i.e. under 4% of the total. **The remaining ~96%
is model generation.**

### Why the 5-second target is not reachable as specified

It is not a tuning problem. Generating a grounded, cited answer with
`claude-opus-5` through AgentRouter takes tens of seconds; the Gateway allocates
streaming routes a 5-minute client timeout for exactly this reason
(`server.go:95`). Nothing inside this system's control turns 27 seconds of token
generation into 5.

### What to do — remediation plan

The ticket permits a criterion to be missed "if documented with a remediation
plan". This is that plan.

1. **Re-specify the criterion as time-to-first-token, not time-to-complete.**
   That is the number a streaming UI actually exposes to a user, and it is the
   metric GOA-032 already adopted for speaking when it hit the identical
   problem: "the user waits ~3s instead of ~77s to see something, so that is
   what this asserts on." Chat has no equivalent metric today — adding one is
   the first concrete step.
2. **Cache aggressively at the RAG layer.** Already present and already helping:
   the max of 99.9s versus a p50 of 26.9s is largely cold-versus-warm.
3. **Consider a smaller model for straightforward lookups.** Grounded factual
   answers over retrieved chunks do not obviously need the largest model.

Until (1) exists, this criterion should be recorded as **known-breached with a
measured number**, not silently widened.

---

## 3. Speaking is STT-bound, and the sidecar is a single shared CPU

**Severity: medium.** Inside its SLO today, with no headroom to grow.

### Evidence

| | ms |
|---|---|
| Time to first transcript, P50 | 19,414 |
| Time to first transcript, **P95** | **25,406** |
| Session complete, P95 | 49,774 |
| WebSocket upgrade success | **100%** (30 sessions) |
| Empty transcripts | **0** |

Budget in `slo.go` is 45,000ms for time-to-first-criterion; **25.4s leaves ~44%
headroom** at 2 concurrent sessions.

### Why it is still a bottleneck

`services/speech` runs faster-whisper `small`, int8, on CPU, as a **single
container with no replicas**. `slo.go` records the transcription ratio as
0.344–0.480 of audio duration, worst on short utterances. Two concurrent
sessions were fine; the ticket's specified 20 would put 20 concurrent
transcriptions through one CPU-bound process, and the ratio would degrade
super-linearly once cores saturate.

This run **did not test that** — speaking ran at 2 VUs under the budget scaling,
so the figure above is a floor, not a ceiling.

### What to do

1. **Measure the sidecar's saturation curve directly** — 1, 2, 4, 8, 16
   concurrent transcriptions of a fixed clip — before assuming 20 sessions work.
   That is a cheap test: no LLM spend, just the sidecar.
2. **Scale `speech` horizontally.** It is stateless per request; nothing stops
   `deploy: replicas` plus round-robin.
3. **Keep the ratio as the alerting metric, not an absolute.** `slo.go` already
   argues this correctly: a millisecond ceiling that passes a 30s Part 1 answer
   fails every two-minute Part 2 answer for reasons unrelated to regression.

---

## Honourable mention — the thing that was NOT a bottleneck

**Zero server errors, zero auth failures, zero empty transcripts, zero essay
agent failures, 787/787 checks passed.** Under 63 concurrent VUs for 10 minutes
the system returned no 5xx at all. Match P95 was 2,131ms against the full
3,793-programme catalogue, so the `/match` batch rewrite is holding up — the
fan-out pathology the ticket warned about did not reappear at this catalogue
size, though 84% of requests being refused means it was not pushed hard.

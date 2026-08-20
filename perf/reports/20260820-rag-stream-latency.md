# Ask Dalil updated RAG streaming latency

Date: 2026-08-20 (Africa/Cairo)

## Result

The updated path makes the interface responsive immediately, but it does not make
uncached answers fast. In the selected ten-sample end-to-end RAG run, the first
`routing` status event arrived in **27.5 ms p50 / 212.3 ms p95**, while the first
answer token arrived in **17.68 s p50 / 49.97 s p95**. Full completion was
**20.01 s p50 / 52.63 s p95**.

All ten selected samples used orchestration's deterministic RAG route and all ten
delivered a valid SSE stream. One sample was a fast evidence-threshold abstention;
generated answers and abstentions are separated below.

## Focused run under light overlap

Source: `20260820T155059Z-rag-stream-latency.json`

Run shape: 10 cache-cold, unique questions with valid UUID user IDs. Every question
was selected to satisfy the deterministic RAG predicate and was sent to `POST
/chat`, which then streamed from RAG's `POST /query/stream` endpoint. Calls were
sequential inside this worker, but a shell-wrapper timeout left an earlier ten-call
worker running at the same time (`20260820T155016Z-rag-stream-latency.json`). The
environment therefore had up to two concurrent callers; this is a light-load probe,
not an isolated single-user measurement.

| Milestone | n | p50 | p95 | max |
|---|---:|---:|---:|---:|
| Response headers | 10 | 27.5 ms | 212.1 ms | 291.6 ms |
| First UI status (`routing`) | 10 | 27.5 ms | 212.3 ms | 291.9 ms |
| Route metadata | 10 | 47.2 ms | 416.9 ms | 457.2 ms |
| Retrieval status | 10 | 47.3 ms | 417.1 ms | 457.3 ms |
| Generation status | 9 generated | 2.76 s | 8.92 s | 10.39 s |
| First answer token, all outcomes | 10 | 17.68 s | 49.97 s | 60.82 s |
| Full stream, all outcomes | 10 | 20.01 s | 52.63 s | 64.62 s |
| First answer token, generated only | 9 | 21.53 s | 51.17 s | 60.82 s |
| Full stream, generated only | 9 | 24.24 s | 53.97 s | 64.62 s |
| Abstention | 1 | 425.5 ms first token | — | 442.5 ms complete |

Delivery rate in the selected run was **10/10**; the overlapping sibling run
delivered **9/10**, with one upstream failure after 91.18 s. The immediate status
event is what drives the visible frontend activity animation, so the UI can
acknowledge the request in under 0.3 s in this run even when answer text takes tens
of seconds.

## Direct RAG and cache diagnostic

Source: `20260820T154030Z-rag-stream-latency.json`

This exploratory run used eight unique direct RAG calls, one cache seed, five
identical cache hits, and six mixed `/chat` questions. The mixed `/chat` part is
diagnostic only: one scholarship question correctly routed to opportunity matching,
where the original benchmark's non-UUID user ID caused a 500. The focused
run above uses valid UUIDs and only deterministic RAG questions.

| Segment | Attempts | Delivered | First token p50 / p95 | Total p50 / p95 |
|---|---:|---:|---:|---:|
| Direct uncached generation | 6 | 4 | 13.84 s / 30.47 s | 16.36 s / 38.09 s across all attempts |
| Direct evidence abstention | 2 | 2 | 237 ms / 317 ms | 238 ms / 318 ms |
| Exact cache hit | 5 | 5 | 30.0 ms / 30.4 ms | 30.6 ms / 31.4 ms |

The direct generation row contains a real defect: **2 of 6 generation attempts
completed server-side with `answer_tokens=512`, but emitted no token event to the
client**. Their total durations were 9.15 s and 38.74 s. They are counted as
delivery failures, not silently removed. The likely boundary is
`_invoke_via_sdk`: it builds the answer only from `stream.text_stream` chunks and
does not recover text from the final message when the AgentRouter-compatible stream
finishes without text deltas.

The cache result is strong: after a 10.88 s seed call, exact repeats completed in
9.1–31.4 ms. This only helps repeat queries; it does not improve novel questions.

## Comparison with the previous measurement

The previous recorded chat load test (`perf/reports/bottlenecks.md`) reported
**26.92 s p50 / 59.89 s p95** completion. This focused sequential run measured
**20.01 s p50 / 52.63 s p95**, directionally 25.7% lower at p50 and 12.1% lower at
p95.

This is not an apples-to-apples regression claim: the old figure came from a larger
concurrent load test, while the new figure is one worker from a two-worker interactive
probe. The defensible conclusion is that perceived responsiveness improved
dramatically because status streaming is immediate; provider generation remains a
heavy-tailed bottleneck and still misses the old five-second completion target.

## Findings and next fixes

1. **Keep the UI SLO split.** Measure acknowledgement/status, first answer token,
   and completion separately. A single completion number hides the main UX gain.
2. **Repair empty provider streams.** When no text delta arrived, extract text from
   `stream.get_final_message()` and send it through the callback before completing.
   Add a test for “final message has text, text stream has no chunks.”
3. **Reduce provider tail latency.** Test a smaller grounded-answer model and cap
   answer length below the current 512-token ceiling. AgentRouter retries were
   visible on the slowest calls.
4. **Expand the deterministic route carefully.** “Application documents” and
   “uni-assist application process” fell back to LLM classification and added
   24.6–30.0 s before retrieval. Add explicit unambiguous terms with routing tests.
5. **Fix telemetry Redis configuration.** Background telemetry repeatedly tried
   `redis-gateway:6379`, which did not resolve in this compose runtime. It did not
   block responses, but it produces noise and loses measurements.

## Reproduction

From `GOA/`, with `rag`, `orchestration`, Postgres, Redis, LocalStack, Ollama, and
valid AgentRouter credentials running:

```powershell
py -3.11 perf/rag_stream_latency_bench.py `
  --cold-runs 0 `
  --cache-runs 0 `
  --chat-runs 10 `
  --timeout 120
```

The harness writes raw per-event timings and percentile summaries to
`perf/reports/<UTC-run-id>-rag-stream-latency.json`. Ten samples are adequate for a
diagnostic run, not an SLO certification. Ensure no prior harness process is
running, then use at least 30 sequential samples and a separate
controlled-concurrency run before setting production thresholds.

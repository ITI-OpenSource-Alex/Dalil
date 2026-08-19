# GOA-036 — system-wide load test

**Run `20260811T032552Z`.** 10 minutes sustained, against the local
docker-compose stack, entirely through the Gateway.

Artefacts for this run share that timestamp prefix in `perf/reports/`, and the
whole set is mirrored to `s3://goa-e2e-reports/perf/20260811T032552Z/`.

---

## 1. What was run, and what it is not

| | |
|---|---|
| Target | local docker-compose, `http://gateway:8080` from inside `goa_default` |
| Duration | 10 minutes sustained |
| VUs | 63 total — chat 10, speaking 2, essay 1, match 50 |
| Identities | 50 real accounts, registered + profiled + upgraded through the Gateway |
| Catalogue at run time | 3,805 programmes (3,793 non-seed), 3,979 RAG chunks, 19 visa rows |
| Spend | **$2.38** ($3.58 → $5.96 on `/admin/costs`) |
| k6 exit | 99 — one threshold crossed, deliberately not relaxed |

**There is no staging environment.** GOA-021 never received AWS credentials and
`deploy-staging.yml` has been paused since 2026-07-27. Both this ticket and
GOA-030 carry a NO-AWS warning redirecting them to local compose, which is what
was used. Every number below describes one developer machine, and the absolute
values should be read as a shape rather than as a production SLO.

### Concurrency is not the ticket's number, and why

The ticket specifies 100 chat + 20 speaking + 10 essay + 50 match. Its own
ROUTER IMPACT note rescopes that:

> Rescope by spend, not by capability: pick a run size costing ~$5–10, document
> the observed P95 per endpoint, and state that concurrency was bounded by
> project budget rather than by the system.

So the shape was preserved and the magnitude scaled to 10% (`LOAD_SCALE=0.1`),
except `match`, which makes no LLM call and therefore ran at the full specified
50 VUs. At $2.38 the run came in under the ticket's own $5–10 guidance.

### Which bound was binding

The ticket requires this to be stated. **Neither spend nor catalogue size was
the binding constraint. The Gateway's own per-feature rate limits were.**

| Limiter | Configured | Effect on this run |
|---|---|---|
| `/api` global | 60 / user / minute | shaped the think times |
| `CHAT_QUERIES_PER_HOUR` | 20 | 10 chat VUs → ~200/hour ceiling; 181 completed in 10 min |
| `OPPORTUNITY_SEARCHES_PER_HOUR` | 20 | **2,475 of ~2,936 match requests refused** |
| `ESSAY_EVALS_PER_HOUR` | 5 | **~110 of 115 evaluations refused** |

The catalogue was fully ingested (3,793 non-seed programmes), so the fan-out
question the ticket's Option B warning is about *could* have been answered — but
the limiter refused most requests long before catalogue size mattered. That is
itself the headline finding; see `bottlenecks.md`.

---

## 2. Latency per endpoint

All figures from `20260811T032552Z-k6.json`, milliseconds.

| Endpoint | P50 | P90 | P95 | Max | Ticket criterion | Verdict |
|---|---|---|---|---|---|---|
| chat (`POST /api/chat`) | 26,923 | 47,916 | **59,885** | 99,896 | P95 < 5,000 | ❌ **breached, 12×** |
| match (`POST /api/opportunities/query`) | 3.6 | 211 | **2,131** | 10,222 | P95 < 5,000 | ✅ passed |
| essay upload | 25.3 | 40.6 | 56.6 | 213 | — | ✅ |
| essay evaluate | 3.1 | 7.8 | 12.7 | **23,381** | P95 < 30,000 | ⚠️ **not meaningful — see below** |
| speaking, time to first transcript | 19,414 | 24,531 | **25,406** | 26,050 | (see below) | ✅ passed |
| speaking, session complete | 39,318 | 49,379 | 49,774 | 50,271 | — | — |

**P99 is not reported.** `--summary-export` emits p50/p90/p95/min/max/avg only.
Every raw sample is in the Prometheus remote-write series
(`k6_*`, retained on the local Prometheus) if a p99 is needed; inventing one
from the exported summary would be a fabricated number.

### The essay percentile is an artefact, not a result

`essay evaluate P95 = 12.7ms` is **not** a latency measurement and must not be
read as passing the 30-second criterion. 115 evaluations were attempted by a
single VU against a 5-per-hour limiter, so roughly 110 samples are the latency
of an immediate 429. The handful that actually ran completed with **4 of 4
criteria every time** (`goa_essay_criteria_completed` p50 = 4, max = 4) and the
slowest took **23.4 seconds**.

So the honest statement is: *the essay evaluations that were allowed to run
completed in ≤23.4s with all four criteria, which is inside the ticket's 30s
target; the percentile itself is dominated by rate-limited rejections.*

23.4s is also notably better than the ~50s recorded before this work, because
the `ANTHROPIC_TIMEOUT_SECONDS` fix (25 → 120) stopped agents being cut off and
retried.

### The speaking criterion the ticket names does not exist

The ticket asks for "P95 speaking latency < 3s". No quantity in this system
corresponds to that. `services/speaking/internal/speaking/slo.go` defines the
measured budgets, and the closest v3 analogue is time-to-first-transcript, which
is STT-bound. Measured **P95 = 25.4s against the 45s budget** — comfortably
inside it. Thresholds in `load-test.js` are pinned to `slo.go` rather than to the
ticket's number, so the test cannot pass while the service breaches.

---

## 3. Throughput, errors and correctness

| Metric | Value |
|---|---|
| HTTP requests | 3,342 |
| Iterations | 3,256 |
| Throughput | ~5.6 req/s sustained |
| Data received / sent | 80.9 MB / 17.3 MB |
| **Server errors (5xx / transport)** | **0** |
| Rate-limited (429) | 2,585 |
| Auth/entitlement failures (401/403) | 0 |
| **k6 checks** | **787 passed, 0 failed** |
| WebSocket sessions | 30 |
| **WebSocket upgrade success rate** | **100%** (threshold `rate>0.99` passed) |
| Empty transcripts for real speech | **0** |
| Essay agent failures | **0** |

**Error rate against the ticket's "< 1%" criterion: 0%.** 429s are excluded
deliberately and counted separately — a rate limiter refusing traffic is the
Gateway working, not the system failing, and folding the two together produces a
number nobody can act on.

**Lambda cold starts: N/A.** Nothing in this system runs on Lambda. Reported as
not-applicable with the reason rather than as zero, per the standing rule that
"unknown" and "zero" must never collapse.

---

## 4. Threshold results

`True` in the k6 summary means *crossed*, i.e. failed.

| Threshold | Crossed? |
|---|---|
| `goa_chat_duration_ms p(95)<5000` | **YES** — measured 59,885 |
| `goa_match_duration_ms p(95)<5000` | no |
| `goa_essay_evaluation_duration_ms p(95)<30000` | no (but see §2) |
| `goa_speaking_time_to_first_transcript_ms p(95)<45000` | no |
| `goa_speaking_ws_upgrade_success rate>0.99` | no |
| `goa_speaking_empty_transcripts count==0` | no |
| `goa_essay_agent_failures count==0` | no |
| `goa_server_errors count<10` | no |

**No target was relaxed to make this run pass.** The chat threshold is left at
the ticket's 5 seconds against a measured 59.9 seconds, so the run fails loudly
and the number is on the record. GOA-032 set that precedent when its own
capacity-bound run failed: *"the test demanded the lie."*

---

## 5. Evidence and how to reproduce

```bash
docker compose up -d
LOAD_SCALE=0.1 LOAD_DURATION=10m ./perf/run-load-test.sh
```

Artefacts, all prefixed `20260811T032552Z-`:

| File | Contents |
|---|---|
| `-k6.json` | full k6 summary |
| `-catalogue.csv` | programmes / non-seed / documents / visa rows at run time |
| `-tokens-meta.json` | how many accounts were provisioned and replicated |
| `-costs-before.json` / `-costs-after.json` | `/admin/costs`, the spend delta |
| `-prometheus-{gateway,rag,speaking,writing,orchestration}-{before,after}.txt` | per-service `/metrics` snapshots |
| `GOA-036-prometheus-window.txt` | queried Prometheus state for the load window |

k6 streamed live to Prometheus via `experimental-prometheus-rw`, which is the
local stand-in for the ticket's "k6 CloudWatch output plugin — latency percentile
charts visible in CloudWatch during the test run". The series are queryable as
`k6_goa_*` and the Grafana dashboard at `localhost:3001` renders them live.

> **Dashboard PNG not captured.** The ticket asks for a CloudWatch dashboard
> snapshot as a PNG. There is no CloudWatch, and this Grafana 10.4.0 image ships
> without the image-renderer plugin, so it cannot export PNGs server-side; no
> screenshot could be taken in this environment either. `GOA-036-prometheus-window.txt`
> holds the same information as queried numbers instead. Recorded as a gap
> rather than presented as satisfied.

---

## 6. What this run does not tell you

Stated so nobody reads more into it than it supports.

- **Not a production measurement.** One laptop, one CPU-bound Whisper sidecar,
  one shared Postgres. Absolute latencies describe this machine.
- **The system was never saturated.** The rate limiter refused most load, so no
  capacity ceiling was reached and no queueing behaviour was observed.
- **Part 3 of the speaking interview is not covered.** Sessions end via
  `abandon` after Part 1 turns, because a full interview is 11–14 minutes by
  design. Adaptive follow-up generation and the prep/long-turn timers are
  untested here.
- **The `/match` fan-out question is still open.** The catalogue was large enough
  to answer it, but 84% of match requests were refused before reaching RAG.
- **GOA-024's scholarship matcher was not exercised.** The ticket flags it as
  carrying the same pathology `/match` had; there is no Gateway route driving it,
  so this run says nothing about it.

# GOA-030 — live-stack journey suite

Four end-to-end user journeys driven against a **running docker-compose stack
through the Gateway**. Nothing here is mocked.

```bash
# from the repo root
docker compose up -d
ollama list | grep nomic-embed-text      # RAG embeds through Ollama on the HOST

cd services/frontend
npx playwright test -c playwright.journeys.config.ts
```

## Why this is separate from `test/e2e/`

`test/e2e/` is a **mocked UI contract suite**. It intercepts its backend with
`page.route`, seeds a placeholder cookie the Next.js middleware accepts because
it only checks for presence, and runs in seconds with no stack at all. That is
the right shape for a per-commit gate and it runs in CI.

`test/journeys/` is the opposite in every respect: every account is registered
through the real registration endpoint, every request reaches a real service,
and the assertions are about ingested catalogue data and real model output. It
costs minutes and real LLM spend per run.

Merging them would mean either running the mocked suite against a stack it does
not need, or gating every commit on a suite CI cannot run.

## What each journey asserts

| Journey | Asserts |
|---|---|
| 1 — discovery | Registration, profile, CV upload, then matches backed by a **non-seed** MastersPortal row with a real `source_url` and `dataSource: "scraped"`; the source-linked financial item when visa data exists |
| 2 — visa citation | A student-visa question is answered citing the **official** government/embassy host that was actually ingested — read from the data at runtime, never hardcoded |
| 3 — essay | Four criteria complete with feedback, under GOA-134's band contract (band present only at ≥3 criteria; absent, never zero, below that) |
| 4 — speaking | A protocol-v3 interview through the Gateway socket: examiner TTS, real STT transcript, and the session attributed to the **token's** user rather than the client-supplied `userId` |

## Things that will bite you

**There is no staging environment.** Both GOA-030 and GOA-036 were written
against one; GOA-021 never received AWS credentials and
`.github/workflows/deploy-staging.yml` has been paused since 2026-07-27. These
run against local compose, which both tickets' own warnings redirect them to.

**Profiles replicate asynchronously.** The User service publishes to SQS and RAG
consumes into `local_user_profiles`. Until that lands, `/match` answers **425
Too Early** by design. `matchOpportunities()` retries 425 and only 425 — a 500
or a 429 fails immediately, because retrying those would turn a real defect into
a slow pass.

**The Gateway limits `/api` to 60 requests per user per minute.** Every journey
holds its own freshly registered account for that reason. A shared account
exhausts the budget and reports 429s as feature failures.

**Journey 4 does not cover Part 3.** A full three-part interview is 11–14
minutes *by design* — the 60-second preparation timer is a scoring rule the
server refuses to let a client skip, and the long turn has a 60-second floor.
The journey uses the `abandon` transition, which scores what exists and records
the rest as absent. That covers upgrade → proxy → bank → TTS → STT → persist,
and leaves Part 3's adaptive generation uncovered. Stated here rather than
implied.

**Journey 4 drives the socket from inside the browser.** Not for convenience:
the cohesion requirement is that a browser can reach it, and opening the
WebSocket from the page context proves the handshake, the cookie and the
Gateway's JWT check at upgrade time all behave as they do for a real user.

## Evidence produced by every run

- `test-results/journeys/{timestamp}/summary.json` — pass/fail per journey,
  total duration, Playwright version, every step timing
- Screenshots, videos and Playwright traces for any failing step
- The whole directory uploaded to `s3://goa-e2e-reports/tests/e2e/{timestamp}/`
  (LocalStack — same object layout the ticket specifies, so a real account is an
  endpoint change and nothing else)
- `goa_e2e_step_duration_ms{journey,step}` in Prometheus via the Pushgateway.
  The ticket asks for a CloudWatch custom metric with those exact labels; there
  is no CloudWatch, so the metric keeps its name and backend changes.

Query it:

```bash
curl -s 'http://localhost:9090/api/v1/query?query=goa_e2e_step_duration_ms'
```

## Not in CI, and why

Running these on a GitHub runner would need the full stack, an Ollama model, a
funded LLM key and an ingested catalogue. Without the catalogue the journeys
fail on assertions about data the runner has no way to have. The mocked suite
is the CI gate; this is a pre-release gate run against a real stack, by hand.

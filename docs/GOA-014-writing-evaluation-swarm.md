# GOA-014 — Writing evaluation swarm

| Field | Value |
|---|---|
| Service | Writing |
| Type | AI/Agents |
| Language | Python |
| Priority | P1 |
| Story points | 4 |
| Dependency | GOA-008 — Writing service scaffold |
| Status | Implemented; live-provider evaluation is opt-in |

## Outcome

The Writing service evaluates computer-typed IELTS essays directly with four independent Claude agents: Task Response, Cohesion, Vocabulary, and Grammar. A shared coordinator launches the agents concurrently, emits completed criteria to an SSE queue, calculates the IELTS overall band, persists the full JSON result, and replays identical evaluations from a database-backed cache.

There is no image or OCR stage. Character-level annotations expose the required `text`, `issue`, and `suggestion` values plus zero-based, end-exclusive `start` and `end` offsets.

## API contract

`POST /essays/evaluate` accepts:

```json
{
  "userId": "user-123",
  "essayText": "Typed IELTS essay text...",
  "submissionType": "computer_based",
  "examType": "academic_task_2"
}
```

It returns `essay_id`, four `evaluations`, `overall_band`, and `from_cache`. Each evaluation contains:

```json
{
  "criterion": "grammar",
  "band_score": 6.5,
  "feedback": "...three numbered sentence-level examples...",
  "highlighted_issues": [
    {
      "text": "exact essay substring",
      "issue": "description",
      "suggestion": "revision",
      "start": 42,
      "end": 63
    }
  ]
}
```

`POST /essays/{id}/evaluate` returns `text/event-stream` with four `criterion` events as tasks finish, followed by one `complete` event. An `error` event terminates a failed swarm.

## Acceptance and checks

- [x] Four public async functions exist: `evaluate_task_response`, `evaluate_cohesion`, `evaluate_vocabulary`, and `evaluate_grammar`. Checked by `tests/unit/test_writing_agents.py`.
- [x] The coordinator launches all four through one `asyncio.gather`; a wall-clock test proves concurrent execution.
- [x] Agent results enforce criterion, band `0.0–9.0`, feedback, and highlighted issues through Pydantic schemas.
- [x] Feedback always incorporates exactly three model-returned sentence-level examples.
- [x] Inline issue substrings are verified against the essay and converted to character offsets.
- [x] `POST /essays/evaluate` evaluates typed JSON input directly and stores a new essay.
- [x] Migration `003_add_essay_evaluation.sql` adds `evaluation_result JSONB`, `exam_type`, and the cache key/index.
- [x] `POST /essays/{id}/evaluate` streams partial criterion and final events.
- [x] Overall band is the four-band mean rounded to the nearest `0.5` with decimal half-up behavior.
- [x] Each request creates a Langfuse root trace with `user_id`, `essay_id`, and `task_type` metadata.
- [x] Fresh and cached requests create exactly four criterion child spans logging band, token counts, and latency.
- [x] `goa_writing_agent_band_score{criterion=...}` observes every returned band.
- [x] `goa_writing_evaluation_latency_ms` measures full four-agent wall-clock latency and includes a `30000` ms bucket for the P95 SLO.
- [x] `goa_writing_cache_hit_rate` is updated after every completed request.
- [x] Structured JSON logs contain user, essay, bands, overall band, wall time, cache source, tokens, and estimated cost.
- [x] Submitting identical content/model/task settings replays persisted output without a second provider call.
- [x] Unit and local integration checks cover concurrency, bounds, rounding, response shape, persistence, SSE, tracing, metrics, and caching.
- [x] A five-essay golden dataset and `>80%` within-`±0.5` gate exist under `tests/evaluation`.
- [x] A manually dispatched paid CI workflow validates the real Anthropic model and fails when its API secret is absent.
- [x] Docker and service environment templates include every Anthropic, Langfuse, model, timeout, and cache setting without committing secrets.
- [x] Terraform Secrets Manager declares the Writing Langfuse public key, secret key, and host alongside the Anthropic key.
- [x] Prometheus scrapes `writing:8000/metrics` and evaluates a five-minute P95 recording rule plus 30-second SLO alert.
- [x] `scripts/verify_goa014_deployment.py` validates live metric export, the latest one-root/four-child Langfuse trace, child metadata, scrape health, and P95.
- [ ] Live Anthropic golden accuracy has been executed in the target CI environment. Enable repository variable `RUN_WRITING_EVAL=1` and secret `ANTHROPIC_API_KEY`; the CI job then enforces the threshold.
- [ ] A deployed Langfuse instance has been inspected manually for trace ingestion. The local integration check verifies the required one-root/four-child topology without external network access.
- [ ] Production Prometheus has demonstrated P95 below 30 seconds. The code exports the correct wall-clock histogram; this SLO requires deployed traffic.

## Configuration

- `ANTHROPIC_API_KEY`
- `WRITING_MODEL` (default `claude-sonnet-4-6`)
- `ANTHROPIC_TIMEOUT_SECONDS` (default `25`)
- `WRITING_CACHE_VERSION` (bump to invalidate prior evaluations after prompt changes)
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

## Commands

```bash
cd services/writing
python -m pytest -q
RUN_WRITING_EVAL=1 ANTHROPIC_API_KEY=... python -m pytest tests/evaluation -m evaluation -q
python scripts/verify_goa014_deployment.py --user-id user-123 --essay-id 42
```

## Verification record

Local verification on 2026-07-15:

- `python -m pytest -q`: **35 passed, 2 skipped**. The skips are the opt-in infrastructure E2E and paid five-essay provider evaluation.
- `python -m compileall -q app tests`: passed.
- `docker compose config --quiet`: passed, including the Writing scrape and alert mounts.
- GitHub Actions workflow YAML parse: passed.
- `git diff --check`: passed.

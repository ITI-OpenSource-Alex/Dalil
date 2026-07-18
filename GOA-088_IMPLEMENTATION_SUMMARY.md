# GOA-088 – Structured Opportunity Ingestion

## Overview

GOA-088 adds a structured data path to the ingestion service, alongside the existing unstructured
document/chunk pipeline. The goal: give the RAG service queryable fields (minimum ECTS, IELTS,
GPA, degree level, scholarship deadlines, award amounts) instead of only vector-searchable text
chunks, so downstream matching logic (profile matcher, scholarship matcher) can filter on real
values rather than relying purely on semantic search.

High-level architecture: two ingestion adapters (MastersPortal, DAAD) extract structured records
from the same HTML they already parse for chunk content. Those records are validated and persisted
through two new authenticated internal endpoints on the RAG service, backed by two new Postgres
tables. This mirrors the dual-write pattern already established by GOA-086 for visa requirements.

## What Was Actually Implemented

**Database** — two new/altered tables, four migrations (numbered `011`–`014`; renumbered during
the `dev` merge to avoid colliding with migrations `009`/`010` that already existed on `dev` for an
unrelated feature):
- `scholarship_programs` (new table): name, provider, country, degree_level, award_amount,
  deadline, eligibility (JSONB), citizenship_eligible, min_gpa, min_ielts, source_url,
  content_hash, last_scraped_at, updated_at. Unique on `(provider, name)`.
- `program_requirements` (existing table, extended): added `content_hash`, `source_url`,
  `last_scraped_at`, `updated_at`, and a unique constraint on `(university, degree_level, country)`
  — none of this existed before GOA-088; without it the upsert endpoint below could not function.

**New schemas** (`services/rag/app/schemas/`): `program_requirements.py` and
`scholarship_programs.py` — Pydantic request models matching the tables above field-for-field.

**New services** (`services/rag/app/services/`): `program_requirements_service.py` and
`scholarship_programs_service.py` — atomic `INSERT ... ON CONFLICT ... DO UPDATE` upserts, cloned
from the GOA-086 `visa_service.py` pattern. Unlike the visa pattern, these always advance
`last_scraped_at` on conflict (not gated on `content_hash` matching) — a deliberate deviation
required by this ticket's own idempotency wording.

**New endpoints** (`services/rag/app/api/`): `POST /internal/program-requirements` and
`POST /internal/scholarship-programs`, both authenticated via the existing `X-Internal-Api-Key`
mechanism, both registered in `app/main.py`.

**Adapter changes** (`services/ingestion/app/adapters/`):
- `masters_portal.py` — corrected a stale country-ID in the target URL (was resolving to the
  Netherlands, not the UK); added a third crawl tier (country → university → programme) via a
  `scrape()` override, since the shared base adapter only supports a single discovery hop;
  added structured `program_requirements` extraction (degree level from page title, ECTS/GPA/IELTS
  from page text) and a `scrape_structured()` entry point.
- `daad.py` — added structured `scholarship_programs` extraction (deadline, award amount,
  eligibility, degree level, IELTS/GPA) and a `scrape_structured()` entry point. Verified against a
  real captured DAAD page, which surfaced and fixed three extraction bugs (degree level picking a
  prerequisite instead of the awarded degree; a title-suffix parsing assumption; section-boundary
  text bleeding between fields).
- `chevening.py` — **unchanged**. No structured extraction was implemented for this adapter.

**Shared helper**: `services/ingestion/app/core/content_hash.py` — extracted from
`german_embassy_cairo.py` so both new adapters (and the original GOA-086 adapter) share one hashing
implementation instead of duplicating it.

**Ingestion client** (`services/ingestion/client.py`): `upsert_program_requirement()` and
`upsert_scholarship_program()` added, mirroring the existing `upsert_visa_requirement()`.

**Orchestrator**: **not modified.** `run_orchestrator.py` does not call either new client function
and does not reference `program_requirements` or `scholarship_programs` anywhere. See "Data Flow"
below — this is the most important gap for anyone picking this ticket back up.

**Metrics/logging**: no new Prometheus counters or structured logging were added for this feature.

**Testing infrastructure**: adapter test fixtures were moved out of inline Python string literals
into `services/ingestion/tests/fixtures/<adapter>/*.html` files, with a `fixtures.md` provenance
log. This applies to the DAAD and MastersPortal test files only.

## Data Flow

**What actually runs end-to-end today:**

```
MastersPortalAdapter.scrape() / DAADAdapter.scrape()
  → structured record attached to the same dict as the chunk content
  → (nothing consumes it further — the orchestrator only reads the chunk content)
```

**What exists but is not yet wired together:**

```
MastersPortalAdapter.scrape_structured() / DAADAdapter.scrape_structured()
  → list[dict] of structured records
  → client.upsert_program_requirement() / client.upsert_scholarship_program()   [exists, unused]
  → POST /internal/program-requirements / /internal/scholarship-programs        [exists, reachable]
  → program_requirements_service.py / scholarship_programs_service.py           [exists]
  → PostgreSQL: program_requirements / scholarship_programs tables              [exists]
```

The two adapters can independently produce structured records (`scrape_structured()`), and the RAG
service can independently accept and persist them (the endpoints work if called directly). What's
missing is the connective step: `run_orchestrator.py` popping the structured records out of each
adapter's output and calling the client functions during a real ingestion run — the same pattern
GOA-086 already uses for `visa_requirements`. A real ingestion run today produces **zero** rows in
`program_requirements` or `scholarship_programs`; only the pre-existing unstructured document/chunk
pipeline runs in production.

Unstructured documents continue to flow through the unchanged path: adapter → chunk dict →
`langchain_core.documents.Document` → existing chunk upsert pipeline. This was not touched.

## Files Worth Reading

- `services/ingestion/app/adapters/masters_portal.py` — 3-tier crawl + structured extraction; read
  `scrape()` and `scrape_structured()` first.
- `services/ingestion/app/adapters/daad.py` — structured scholarship extraction; read
  `_extract_scholarship()` and its helper functions.
- `services/ingestion/app/core/content_hash.py` — shared hashing helper used by all structured
  extraction.
- `services/ingestion/app/services/run_orchestrator.py` — the actual ingestion entry point; note
  what it does *not* call (see Data Flow).
- `services/ingestion/client.py` — HTTP client functions to the RAG internal endpoints, including
  the two new, currently-unused upsert functions.
- `services/rag/app/services/program_requirements_service.py` /
  `scholarship_programs_service.py` — upsert logic; read alongside `visa_service.py` for the
  pattern both were cloned from.
- `services/rag/app/api/program_requirements.py` / `scholarship_programs.py` — thin authenticated
  route handlers.
- `services/rag/app/migrations/013_add_scholarship_programs.sql` /
  `014_add_program_requirements_upsert_support.sql` — the actual schema.
- `services/ingestion/tests/fixtures/fixtures.md` — explains where each test fixture came from.

## Testing

- New test files: `test_daad_structured.py`, `test_masters_portal_structured.py`,
  `test_content_hash.py` (ingestion), `test_program_requirements.py`, `test_scholarship_programs.py`
  (RAG).
- Coverage includes: happy-path extraction for both adapters; every "field not found → `None`, never
  fabricated" edge case (missing deadline, missing IELTS/GPA, ambiguous degree level, non-numeric
  GPA classification); the 3-tier MastersPortal crawl's URL discovery; upsert insert/update
  behavior and idempotency for both new RAG endpoints; auth enforcement on both endpoints.
- One fixture (`real_scholarship_detail_50026200.html`) is a verbatim capture of a real, live DAAD
  page — this is what caught the three DAAD extraction bugs mentioned above; fixture-only testing
  against hand-written HTML did not catch them.
- Final result: **122 passed** in `services/ingestion` (full suite, including GOA-015/GOA-086
  adapters). RAG service: 63 passed, 4 pre-existing unrelated failures (a `test_query.py` bug that
  predates this ticket), 1 deliberately skipped test (unrelated, pending GOA-045).

## Notes for Future Developers

- **The orchestrator wiring is the biggest open gap.** Both adapters can produce structured data;
  nothing currently calls that path during a real run. This is the natural next task — pop
  `program_requirements`/`scholarship_programs` keys out of each adapter's chunk-dict output inside
  `run_orchestrator.py`, exactly as it already does for `visa_requirements`.
- **Chevening was never implemented.** `CheveningAdapter` has no structured extraction at all.
- **No metrics or structured logging for this feature.** No Prometheus counter tracks structured
  upserts; failures in this path (once wired) will not be independently observable from the existing
  chunk-pipeline metrics.
- **Extraction is intentionally conservative.** Every field falls back to `None`/empty rather than
  guessing when the source page doesn't state something unambiguously. This is deliberate — treat
  any change that starts inferring/defaulting values as a design decision, not a bug fix.
- **Degree-level detection has known gaps.** MastersPortal/DAAD degree parsing recognizes common
  spelled-out forms (Master, Bachelor, PhD, Research Grant) but not all abbreviations (e.g. M.Sc.,
  MPhil, MSt) — live testing during implementation found this misses a meaningful share of real
  pages. Not fixed; flagged for whoever extends this.
- **Idempotency semantics differ from the GOA-086 visa pattern on purpose.** The two new services
  always advance `last_scraped_at` on every upsert, even when nothing changed. `visa_service.py`
  does not. This was a deliberate choice per this ticket's stated acceptance criteria — don't
  "fix" one to match the other without checking why they differ first.
- **Crawler reliability issues exist but were left alone.** During implementation, both target
  sites intermittently returned errors (DAAD: WAF/rate-limit blocks; MastersPortal: Cloudflare
  challenge responses) unrelated to the extraction logic itself. Neither `BasePlaywrightAdapter` nor
  the retry/wait-strategy configuration was touched — this was explicitly scoped out and left for a
  separate task.
- **Migration numbers were renumbered once already** (from `009`–`012` to `011`–`014`) to resolve a
  collision with unrelated migrations already on `dev`. If you're deploying this to any environment
  that might have applied the *original* numbering, check `migrations_log` before assuming a clean
  apply.

## Summary

- Adds two new structured tables (`scholarship_programs` new, `program_requirements` extended) with
  authenticated upsert endpoints on the RAG service.
- `MastersPortalAdapter` and `DAADAdapter` can extract structured fields from real pages; verified
  against live content, not just hand-built fixtures.
- `MastersPortalAdapter` also gained a corrected target URL and a new crawl tier to reach programme
  pages at all.
- `CheveningAdapter` has no structured extraction — not implemented.
- The ingestion orchestrator does not yet call the new structured-upsert path — a real ingestion run
  today does not populate either new table. This is the key remaining integration gap.
- No metrics or dedicated logging were added for the structured path.
- Test fixtures were reorganized into files with provenance tracking; 122/122 ingestion tests pass.
- Known, documented limitations: degree-abbreviation coverage, no orchestrator wiring, no Chevening
  support, and pre-existing (unaddressed) crawler reliability issues on both target sites.

# Refactor Sprint: GOA-112 → GOA-116 Implementation Plan

This plan covers all 5 refactor tickets in one pass: GOA-112/113/114 (from [GOA_E2E_Testing_Tickets.md](GOA_E2E_Testing_Tickets.md)) and GOA-115/116 (from [GOA-115-116-Refactor-Tickets.md](GOA-115-116-Refactor-Tickets.md)).

Per our `skeleton-mentor` workflow: **I (ag) scaffold** directory structures, signatures, and behavior-task TODOs at the density each ticket's pattern classification calls for, and **I write and run the test suites directly** (tests are excluded from the skeleton-and-task model — I iterate small misses to green myself, and hand back only genuine design gaps through the three-part feedback format). **You (the developer)** write the implementation logic inside the scaffolds.

## Pattern Calibration (per skeleton-mentor rule 2)

| Ticket | Pattern | Skeleton density | Reasoning |
|---|---|---|---|
| GOA-112 | **REPEAT** | Near-complete | FastAPI POST route + SQLAlchemy insert — you've built these in this exact service (`cvs.py`, `essays.py`) and across Exam/RAG all sprint |
| GOA-113 | **REPEAT** | Near-complete | Router mounting + one key rename — trivial mechanics, the value is in the contract decision, which is already made |
| GOA-114 | **REPEAT** (queries) + one **NEW** decision | Medium | SQL join + response shaping = mastered (see `session_service._shape_speaking_questions`). The schema-gap decision below is the genuinely new thinking |
| GOA-115 | **REPEAT** (pagination) + **NEW** (structured extraction depth) | Medium-sparse | Pagination is the verified DAAD pattern, literally reusable. Field-level extraction with NULL-not-guess discipline is where the real work is |
| GOA-116 | **NEW** | Sparse — interfaces and constraints only | First LLM-extraction adapter in the project. Config-driven design, evidence-quote enforcement, and hallucination guards are all first-of-kind. The logic is entirely yours to write |

**Mastery log (rule 5):** FastAPI routes, pytest mock patterns, Prometheus metrics, and idempotent UPSERTs graduated to REPEAT during GOA-052/018/020. Playwright pagination graduated via the DAAD fix in GOA-015. LLM-as-extractor has no prior instance — it stays NEW until GOA-116 ships clean.

## Execution Order

```
GOA-113 (1pt) → GOA-112 (2pt) → GOA-114 (3pt, needs 113) → GOA-115 (3pt) → GOA-116 (4pt, needs 115)
```

113 first: smallest, unblocks 114, and immediately un-breaks the OPPORTUNITY_SEARCH intent end-to-end. 115/116 last: they're Sprint-2-scoped adapter work with the heaviest surface area.

## Open Questions

> [!IMPORTANT]
> **GOA-114 has a schema gap that must be decided before its implementation starts.** The ticket requires each match entry to carry `programName` and `deadline` — but `program_requirements` (verified against migrations 003 + 008) has **neither column**: only `university, country, degree_level, min_ects, min_gpa, min_ielts, required_citizenship, min_work_experience`. And `/match` scores exclusively against `program_requirements` rows, so a join to `scholarship_programs` won't cover them. Options:
> 1. **Add `program_name` and `deadline` columns to `program_requirements`** (new migration), populated by GOA-115's extraction — my recommendation, since GOA-115 is in this same batch and already parses program pages where the name is available. `deadline` stays nullable (degree programs often have per-intake deadlines, not one date).
> 2. Return `programName` derived from `university + degree_level` and omit `deadline` — no migration, but permanently thinner cards than GOA-019 specifies.
>
> Decision needed before GOA-114 (and it affects GOA-115's extraction field list).

> [!WARNING]
> Column naming: migration 008 renamed `citizenship_required` → `required_citizenship`. GOA-115's ticket text still says `citizenship_required`. Use the **actual current column name** (`required_citizenship`) everywhere.

---

## GOA-113 — RAG `/match`: fix route path + response field name (REPEAT)

### Proposed Changes

#### [MODIFY] [scoring.py](file:///d:/ITI/Graduation%20Project/GOA/services/rag/app/api/scoring.py)
- Move the `/match` route off the `/scoring`-prefixed router onto a new unprefixed `APIRouter` (registered in `main.py`), so the real path becomes `/match` — matching GOA-012's own spec and Orchestration's existing call. `/score` stays at `/scoring/score`, untouched.
- Rename the response key `matches` → `programs` (canonical name = what Orchestration's `client.py` already reads; RAG changes, Orchestration doesn't).
- `# TODO: the /match handler currently returns {"matches": results}. After re-keying to "programs", make sure the sort-by-score-descending behavior is preserved and each entry keeps {programId, result} — GOA-114 builds on exactly this shape.`

#### [MODIFY] [main.py](file:///d:/ITI/Graduation%20Project/GOA/services/rag/app/main.py)
- Register the new unprefixed router.

### Verification Plan (I write and run these)

1. `test_match_reachable_at_bare_path` — `POST /match` returns 200, not 404; `POST /scoring/match` no longer exists (or 404s — asserting the old path is gone prevents a silent duplicate route).
2. `test_match_response_key_is_programs` — top-level key is `programs`, entries sorted descending by score.
3. `test_score_path_unchanged` — `POST /scoring/score` still works (regression guard).
4. **Cross-service integration:** replay GOA-096/ORC-03's scenario — OPPORTUNITY_SEARCH intent through Orchestration yields a non-empty `match_results` SSE event against seeded data. This is the test that was silently impossible before this ticket.
5. **Pre-merge sweep:** `grep -rn "scoring/match\|\"matches\"" services/rag/tests services/rag/app` — any existing RAG test asserting the old path or the `matches` key gets updated **in this same PR**, never left red for a follow-up.

---

## GOA-112 — Writing service: missing `POST /essays` creation endpoint (REPEAT)

### Proposed Changes

#### [MODIFY] [schemas.py](file:///d:/ITI/Graduation%20Project/GOA/services/writing/app/schemas.py)
- Add `EssayCreateRequest {userId, essayText, submissionType (task1|task2), examSessionId (optional)}` and `EssayCreateResponse {id, status}` — field names per GOA-008's original spec, since GOA-018's Orchestration caller sends exactly that shape.

#### [MODIFY] [essays.py](file:///d:/ITI/Graduation%20Project/GOA/services/writing/app/routers/essays.py)
- Add `POST ""` on the existing `/essays`-prefixed router (i.e., bare `POST /essays`), returning 201.
- `# TODO: persist an Essay with status='ready' and return its id. Constraint: the returned id must be immediately usable by the existing POST /essays/{id}/evaluate SSE route with no extra setup — that means extracted_text, submission_type, and exam_type must be populated the same way /essays/evaluate populates them, or the SSE route's cache-key derivation will diverge for created-then-evaluated essays vs directly-evaluated ones.`
- **Audit resolved — no migration needed for exam_session_id:** it already exists in `models.py` (`exam_session_id = Column(String, nullable=True)`) *and* in `migrations/001_create_essays.sql` (`exam_session_id VARCHAR`), and `essays.py` already threads it through several handlers. No model/DB drift. The `EssayCreateRequest.examSessionId` field just maps straight to the existing column. **Also note: `essays.py` already contains partial GOA-112 scaffolding (a TODO at line ~46 and create-path references) — reconcile with what's there rather than adding a parallel route.**

### Verification Plan (I write and run these)

1. `test_create_essay_returns_201_with_id_and_ready_status`
2. `test_create_essay_missing_essay_text_422` and invalid `submissionType` 422
3. `test_create_then_stream_evaluate` — create via new route, immediately open `POST /essays/{id}/evaluate`, assert the SSE stream completes (mocked coordinator). **This is the contract test** — the whole reason the endpoint exists.
4. `test_create_with_exam_session_id_persists` (or is cleanly rejected if the column decision goes the other way — locked to whatever you decide in the TODO)
5. **Cross-service integration:** GOA-018's WRITING intent flow — Orchestration `POST /chat` "evaluate my essay" → Writing receives the create, `writing_url` event carries a working `sseUrl`. Replays GOA-096/ORC-02 which currently 404s.

---

## GOA-114 — RAG `/match`: enrich results with display metadata (REPEAT + one NEW decision)

**Blocked on the Open Question above.** Plan below assumes Option 1 (add columns).

### Proposed Changes

#### [MODIFY] `services/rag/app/migrations/015_add_program_display_fields.sql` — **already exists and is BROKEN; fix it, do not create a new file**
- Audit finding: this migration was already scaffolded (by an earlier pass) and adds `program_name VARCHAR(255) NULL` + `deadline DATE NULL` — the right columns — but it has **three defects that will fail the RAG migration run the moment it executes** (confirmed NOT yet applied: absent from `migrations_log`, columns absent from the live table — the running container predates the file):
  1. `SET program_name = 'MSc Computer Science', deadline = "2024-5-31",` — the date is **double-quoted**, which Postgres parses as an *identifier*, not a string literal → error. Use single quotes `'2024-05-31'`.
  2. That same line has a **trailing comma** before `WHERE` → syntax error independent of #1.
  3. **Up and Down are not separated** — the file runs `ADD COLUMN`, backfills, then `DROP COLUMN` all inline, so a successful run would leave the table with no new columns. Split into a real up migration (add + backfill) and a separate down (drop), per GOA-079's convention. This service's raw-SQL runner applies the whole file — it has no up/down markers, so the down block must live in a separate file or be commented out, not executed inline.
- Fix all three, then confirm `docker compose build rag && docker compose up -d` applies it cleanly and the columns appear live.

#### [MODIFY] [scoring.py](file:///d:/ITI/Graduation%20Project/GOA/services/rag/app/api/scoring.py)
- `# TODO: enrich each /match entry with {programName, university, country, deadline} in a single query — fetch the display columns together with the id list at the top of match_profile (one SELECT, not N per-program lookups; the loop already does one scoring call per program, don't add a second round-trip). Entries whose program row lacks a program_name fall back to university + ' — ' + degree_level rather than null; entries with no row at all are omitted per the ticket.`
- `# TODO (performance — armed by GOA-115): match_profile currently scores every program row SEQUENTIALLY, each with a potential Stage-3 LLM boost. At 3 seed rows that's invisible; at GOA-115's ≥50 rows an uncached /match becomes ~50 sequential scoring runs — tens of seconds and real Anthropic spend per call. Since this ticket already owns this handler: wrap the per-program calculate_score calls in asyncio.gather bounded by an asyncio.Semaphore (start at 5 concurrent). Constraint: preserve result ordering by score and the existing skip-on-error behavior per program. Anything beyond bounded concurrency (SQL-level gate pre-filtering, batch scoring) is explicitly OUT of scope — if post-merge latency measurements still miss the mark, that becomes its own follow-up ticket with real numbers attached, not speculation here.`

### Verification Plan (I write and run these)

1. `test_match_entries_carry_display_fields` — seeded rows return all four fields, non-null.
2. `test_match_null_name_falls_back` — row with NULL `program_name` yields the university-derived fallback, never `null` in the response.
3. `test_match_missing_row_omitted` — a scored id with no `program_requirements` row is dropped, not returned half-empty.
4. `test_no_n_plus_one` — assert query count doesn't scale with program count (mock/spy on the pool).
5. `test_match_scores_concurrently_bounded` — with 12 mocked programs and an instrumented `calculate_score` (records max in-flight count), assert >1 concurrent but ≤ the semaphore cap, and that the response is still sorted by score. Locks in the concurrency fix without depending on wall-clock timing.
6. **Frontend-contract smoke:** the response renders `OpportunityCard`'s four fields with zero client-side lookups (asserted shape-only, per GOA-114's RAG-REF-07).

---

## GOA-115 — MastersPortal deep-scrape refactor (REPEAT pagination + NEW extraction depth)

> [!NOTE]
> **Scope decision (recorded for the audit trail):** A distributed-crawler expansion to ~100k programs (discovery/extraction queue split, proxy rotation, horizontal workers, multi-day runtime) was considered and **rejected**. It contradicted GOA-115's own "prove ~50 first" scope clause, required commercial proxies + real embedding spend + long-running cloud infra that this free-tier project does not have, and carried ToS risk on a commercial site — all to solve a breadth problem the system doesn't actually have. The genuine concern ("50 *random* programs might miss relevant ones") is solved by **targeting, not volume**: filter discovery to the disciplines our users actually apply to. The ~50 cap and single-run synchronous design stand.

**Refinement to the ticket:** discovery is filtered to **Engineering + Computer Science** programs only. This narrows the ~50 to on-persona programs (Egyptian STEM applicants) across the target countries, which is strictly better than 50 unfiltered results and costs nothing extra.

### Proposed Changes

#### [MODIFY] `services/ingestion/app/adapters/masters_portal.py` — **correct path; the real adapters live in `app/adapters/` (one file each), not the legacy top-level `adapters.py`**
- `# TODO (upsert key): dedup and idempotent-upsert on the UNIQUE constraint migration 014 (GOA-088) already added — (university, degree_level, country). Don't invent a new key; the internal upsert endpoint keys on that.`
- `# TODO (discipline filter): point discovery at MastersPortal's Engineering and Computer Science search results, not the generic listing — verify at the live site whether the discipline filter is a URL path segment, a query param, or a facet click (Playwright). Extract from BOTH disciplines and merge/dedupe into one URL set before the cap. If the site exposes finer sub-disciplines (e.g. Software Engineering, Data Science), including them is fine — the goal is "programs a STEM applicant would apply to," not a rigid two-category split.`
- `# TODO (pagination): rework MastersPortalAdapter.extract_urls() to walk result pages exactly the way DAADAdapter's verified fix does — but FIRST verify against the live site whether mastersportal.eu uses ?page=N URLs or infinite scroll; these need different Playwright loops and the ticket explicitly forbids assuming. Cap at 50 distinct program URLs TOTAL across both disciplines (not 50 each — keep the run small and synchronous), dedupe, stop early when a page yields no new links.`
- `# TODO (extraction): for each program detail page, parse the structured fields program_requirements needs — university, country, degree_level, min_ects, min_gpa, min_ielts, required_citizenship (NOTE: post-008 column name), plus program_name/deadline if GOA-114 Option 1 is chosen. Hard constraint: a field not explicitly present on the page is NULL, never a guessed default. Numeric fields must survive locale formats ("120 ECTS", "GPA 3.0/4.0", "IELTS 6.5 overall").`
- `# TODO (quality gate): before upserting, reject pages that are nav-chrome/listing fallbacks — the check must key on presence of real program content (name + at least one requirement field), and rejects must be logged with the URL, not silently skipped.`
- Reuse (unchanged): `polite_delay()`, robots.txt handling, retry/backoff scoping, the GOA-088 internal upsert endpoint, dual-write to `Document` chunks, S3 raw-HTML storage, `goa_ingestion_docs_processed_total{source='mastersportal'}`.

#### [MODIFY] [seed_data.sql](file:///d:/ITI/Graduation%20Project/GOA/evals/seed_data.sql) + [runner.py](file:///d:/ITI/Graduation%20Project/GOA/evals/runner.py)
- The evals seed currently opens with `TRUNCATE program_requirements CASCADE` — once this ticket's ingestion populates ≥50 real rows, running the evals seed locally **wipes them all**. Replace both blanket TRUNCATEs with targeted DELETEs of only eval-owned rows (the `00000000-…-0001`→`…-0020` profile UUIDs and the eval program row). Simultaneously move the eval program off UUID `11111111-…` — migration 008 seeds that exact UUID as TU Munich, and only the truncate has been hiding the collision — to a clearly eval-owned UUID (e.g. `99999999-9999-9999-9999-999999999999`), updated in both `seed_data.sql` and the hardcoded `programId` in `runner.py` in the same commit. Re-run the evals suite after, since this is exactly the kind of two-file consistency edit that drifts.

#### Ticket-retirement step (part of this ticket's DoD, not a follow-up)
- On merge: mark **GOA-111 as retired/absorbed** in [GOA_Sprint_3_Tickets.md](GOA_Sprint_3_Tickets.md) (strike-through + pointer to this ticket, don't delete the historical text) and regenerate the Sprint 3 dependency-graph artifact without it. Leaving GOA-111 live in Sprint 3 planning is how someone duplicates this exact work in three weeks.

### Verification Plan (I write and run these — `test_masters_portal_structured.py` gets **rewritten in this PR**, since it asserts the current shallow adapter's behavior; its fixtures stay, its assertions change with the implementation, never left red for later)

1. Discipline-filter unit: discovery targets the Engineering and CS search results (assert the fetched search URLs/facets are the discipline-filtered ones, not the generic listing), and the two disciplines' URL sets are merged + deduped before the cap.
2. Pagination unit: multi-page fixtures yield distinct URLs across pages, capped at 50 **total** across both disciplines, not stuck on page 1 — including a fixture where page 3 repeats page 2's links (dedupe + early-stop), and one where Engineering and CS return an overlapping program (deduped to one).
3. Extraction unit: fixture detail page → every structured field extracted correctly; second fixture with fields absent → those fields NULL, no invented defaults. Third fixture with locale-formatted numbers parses correctly.
4. Quality-gate unit: listing-page fixture is rejected and logged, not upserted.
5. Idempotency: same fixture run twice → one row, not two (GOA-088 upsert path).
6. Integration: full run against fixtures produces ≥50 `program_requirements` rows + proportional `Document` chunks.
7. **The regression test the ticket exists for:** `POST /score` against a seeded profile returns real, varied gate decisions — not "no matching program" — with the newly populated table.

---

## GOA-116 — Generic LLM-extraction visa adapter (NEW — sparse skeleton, your logic)

> [!IMPORTANT]
> **Hard-won constraints carried over from the GOA-112–115 audit.** Eight real defects were found after those tickets were reported "complete and green" — **four of them were invisible behind passing test suites**. Every item below is a trap GOA-116 can hit in the same way, because it touches the same migration runner, the same DB-to-Pydantic boundary, and the same config/container surface.
>
> **1. Migration 016 hygiene** (three separate bugs hit this exact pattern):
> - String literals are **single-quoted**. `deadline = "2024-5-31"` cost RAG a crash-loop — double quotes make Postgres read an *identifier*.
> - **No inline DOWN block.** This runner executes the whole file; an inline `DROP` undoes the migration it just applied. Put the rollback in a comment or a separate file.
> - **Never leave 016 as an empty placeholder.** An empty `.sql` made the runner raise `'NoneType' object has no attribute 'decode'` and crash-loop the Exam service. RAG's runner now has a guard (added during the audit) that skips empty files *without* marking them applied — but treat that as a safety net, not permission to commit an empty migration.
> - **No platform-specific SQL.** A copy-pasted Supabase `auth.uid()` RLS policy aborted Exam's migration 004 and silently blocked 005 behind it, so `exam_writing_responses` never existed in any environment. This project is plain Postgres with a single `goa` role — ownership is enforced in application code, not RLS.
>
> **2. Coerce types at the DB boundary.** `visa_sources.id` and `visa_requirements` PKs are `UUID` columns, so asyncpg hands back `uuid.UUID` objects. A Pydantic model typed `str` rejects **every real row** — this is exactly how `/match` returned an empty list for every user while all its tests passed (they mocked the id as the string `"user-123"`). If `VisaSource`/`ExtractionOutcome` carry an id, `str()` it where the row is read, and write the regression test with a **real `uuid.UUID`** in the mock, not a string.
>
> **3. New settings go in TWO places, always.** Exam's `speaking_service_url`/`writing_service_url` were added to `config.py` but not to `conftest.py` *and* not to `docker-compose.yml` — the first broke the whole test suite at collection, the second crash-looped the container. If GOA-116 adds any setting (model name, extraction toggle, source-refresh interval), add it to **`services/rag/tests/conftest.py` AND `docker-compose.yml`** in the same commit.
>
> **4. Rebuild, don't just restart.** Docker staleness caused four separate incidents this project, twice during this audit alone (orchestration missing `pybreaker`, exam running a pre-fix image). GOA-116 changes `requirements.txt` (adds nothing new? verify) and adds a migration: **`docker compose build rag ingestion && docker compose up -d`**, then confirm the migration actually applied via `migrations_log` — not just that the container is "Up".
>
> **5. Verify by execution — this is the DoD, not a nicety.** GOA-116's test suite is almost entirely mocked LLM responses, which is precisely the shape that hid four bugs in this batch. A green suite proves the parsing logic, *not* that the adapter works. Before calling it done: run the real adapter against at least one real fetched source, confirm the row lands in `visa_requirements` via a live `psql` query, and confirm `POST /query` returns an answer citing it. If a claim in the completion report isn't backed by a command that was actually run, it isn't verified.

### Proposed Changes

#### [NEW] `services/rag/app/migrations/016_add_visa_sources.sql` — **note the number: 016, not 012**
- Audit: RAG migrations already run through **015**; `012` is taken (`012_seed_egypt_faq_entries.sql`). Confirmed `visa_sources` and `extraction_evidence` exist in **no** current migration — this file is genuinely new, at 016.
- `visa_sources` table exactly per the ticket's SQL, seeded with the 9 sources; `extraction_evidence JSONB` column added to `visa_requirements`. Down migration in a separate file (same raw-SQL-runner constraint as the 015 fix above — no inline down block).

#### [NEW] `services/ingestion/visa_adapter.py`
Sparse skeleton — signatures and constraints only:
- `class VisaSourceAdapter:` with `run(sources: list[VisaSource]) -> list[ExtractionOutcome]`
- `# TODO (fetch): per source row, fetch via httpx or Playwright per fetch_method; reduce HTML to visible text before prompting. Constraint: a fetch failure marks that source failed and continues the run — one dead embassy page must not kill the other 8.`
- `# TODO (extract): call Claude (claude-haiku-4-5-20251001, per GOA-087's tier) with the ticket's extraction prompt. Constraints that are the entire point of this ticket: (1) fields absent from fetched text are null — the model never fills from general knowledge; (2) every non-null field carries a ≤20-word verbatim evidence quote; (3) source_url is ALWAYS overwritten in code with the fetched URL — never trusted from model output; (4) schema-invalid output retries exactly once with the validation error appended, then marks extraction_failed without upserting.`
- `# TODO (validity gate): if fetched text isn't about the expected country/visa type (error page, redirect), extraction_valid=false, all fields null — no extraction from garbage.`
- `# TODO (dual write): upsert via the existing POST /internal/visa-requirements (unchanged, keyed country+visa_type+issuing_body) AND emit the chunked Document, same as every GOA-086 adapter.`
- Langfuse trace per extraction: model, tokens, latency, cost, fields_extracted, fields_null.

#### Blast radius (audit — wider than "just the adapter files + 2 tests")
The 9 bespoke adapters are real files under `services/ingestion/app/adapters/` (`german_embassy_cairo.py`, `campus_france_egypt.py`, `uk_visa_egypt.py`, `fintiba_sperrkonto.py`, `czech_embassy_cairo.py`, `spain_visa_egypt.py`, `italy_embassy_cairo.py`, plus the Chevening/StudyInPoland/StipendiumHungaricum/DAAD/IELTS ones that are **out of scope** — those are scholarship/program adapters, NOT the 9 visa adapters GOA-116 replaces; do not touch them). Removing the 9 visa adapters also requires editing, in the same PR:
- `services/ingestion/app/services/run_orchestrator.py` — deletes 9 imports and 9 entries from the adapter list, adds the single `VisaSourceAdapter`.
- `services/ingestion/handler.py` and `services/ingestion/live_test.py` — any direct references to the deleted classes.
- `services/ingestion/tests/test_orchestrator.py` — asserts the orchestrator's adapter wiring; update to the new single-adapter shape.

#### Test migration (same PR, not a follow-up)
- `test_egypt_adapters.py` and `test_egypt_ingestion_e2e.py` assert the 9 bespoke adapter classes this ticket deletes — they **cannot survive as-is**. Their fixture HTML (real captured embassy pages) is still the best test data in the project: **keep the fixtures, retire the harnesses**, and port each fixture's substantive assertions (which fields a given page yields) into the new generic-adapter test suite below. The PR that removes an adapter class removes/replaces its tests in the same diff — CI never goes red between commits.

#### Sprint 3 re-scope step (part of this ticket's DoD, not a follow-up)
- On merge, annotate in [GOA_Sprint_3_Tickets.md](GOA_Sprint_3_Tickets.md): **GOA-108** re-scopes from "extend `UKVISAEgyptAdapter`" to "add UK maintenance-funds field to the shared extraction schema"; **GOA-109/110** re-scope from "write a new adapter class" (3pts each) to "add a `visa_sources` row + capture the scholarship-exemption nuance in the shared schema" (likely ~1pt each). Update the Sprint 3 dependency-graph artifact to match. The nuances those tickets exist to capture (Stipendium Hungaricum / NAWA exemptions) are **not** absorbed — only their delivery mechanism changed.

#### [MODIFY] Pydantic schema module (shared)
- `# TODO: single source of truth for the extraction output schema, injected into the prompt — the prompt must never restate the schema by hand, or prompt and validator will drift.`

### Verification Plan (I write and run these — the hallucination guards get the heaviest coverage)

1. `test_extraction_populates_fields_with_evidence` — German Embassy fixture + mocked LLM → `proof_of_funds` + APS requirement populated, evidence quotes present per field.
2. `test_absent_field_stays_null` — fixture missing processing-time → null, not a "typical" value. **The anti-hallucination regression test.**
3. `test_source_url_always_overwritten` — mocked LLM returns a different URL → output row carries the config URL. Code-level enforcement, not prompt trust.
4. `test_invalid_output_retries_once_then_fails` — malformed LLM output → exactly one retry with error appended → `extraction_failed`, zero upserts.
5. `test_validity_gate_rejects_wrong_content` — error-page fixture → `extraction_valid=false`, all null.
6. `test_one_source_failure_doesnt_kill_run` — source 3 of 9 raises → 8 outcomes still produced.
7. Integration: dry-run over all 9 seeded sources → 9 would-be upserts; upsert idempotency re-run; the two `POST /query` answer checks (APS → cites `cairo.diplo.de`/`aps-egypt.de`; blocked account → mentions Fintiba/Expatrio); FAQ cache hit without LLM call.
8. `test_visa_source_uuid_coercion` — mock the `visa_sources` row with a real `uuid.UUID` (not a string) and assert the Pydantic model accepts it. This is the regression test for the exact bug class that silently emptied `/match`; a string-mocked test would pass while the live adapter fails on every row.

### Live verification (required before this ticket is called done — not optional)

Mocked tests passing is **not** sufficient evidence for this ticket. Run and paste the output of:

```bash
# 1. migration actually applied (not just "container is Up")
docker compose build rag && docker compose up -d rag
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT migration_file FROM migrations_log WHERE migration_file LIKE '016%';"
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT country, visa_type, issuing_body, fetch_method FROM visa_sources;"

# 2. RAG actually started (a crash-looping service still shows as a container)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8084/health

# 3. the adapter actually extracted something real, end-to-end
docker exec -i $(docker compose ps -q postgres) psql -U goa -d rag_db \
  -c "SELECT country, proof_of_funds, extraction_evidence FROM visa_requirements LIMIT 3;"
curl -s -X POST http://localhost:8084/query -H "Content-Type: application/json" \
  -d '{"question":"Do I need an APS certificate for Germany?","userId":"<uuid>"}'
```

---

## Cross-Cutting (applies to all 5)

- **Tests move with the code they assert, in the same PR.** Three existing suites are invalidated by this batch (`test_masters_portal_structured.py` by 115; `test_egypt_adapters.py` + `test_egypt_ingestion_e2e.py` by 116; possibly RAG tests by 113 — the grep in 113's plan settles it). The rule for all of them: fixtures are preserved, harnesses are rewritten or retired in the same diff that changes the implementation. No PR in this batch merges with a known-red test "to be fixed next."
- **Planning-doc updates are DoD steps, not memories.** GOA-115 retires GOA-111; GOA-116 re-scopes GOA-108/109/110 — each carries its doc-update step inside its own ticket above, so the Sprint 3 backlog and dependency graph can't silently drift from reality.
- **Land this batch before frontend work starts against `/match`.** GOA-114's response-shape choices are only free of backward-compatibility constraints because no frontend consumer exists yet. The execution order already guarantees this — keep it that way if priorities shuffle.

- **Docker staleness:** three separate incidents this project came from editing `requirements.txt`/init scripts without rebuilding images. Every ticket here that touches deps or migrations ends with `docker compose build <service> && docker compose up -d` as an explicit step, and verification runs against the rebuilt container — not just local pytest.
- **Verify-by-execution:** every "it works" claim in a completion report must come from a command that was actually run (test output, curl response, DB query) — this batch's reviews will re-run them.
- **Line endings:** `.gitattributes` now enforces LF for `.sh` — new SQL/py files inherit safely, but don't hand-escape `$$` in standalone `.sql` files (the seed-script lesson from GOA-020).
- **Stuck protocol (rule 3):** "stuck" gets a hint; "stuck: give me the answer" gets the answer. On GOA-116 especially, expect hints — it's the NEW pattern and the learning target of this batch.
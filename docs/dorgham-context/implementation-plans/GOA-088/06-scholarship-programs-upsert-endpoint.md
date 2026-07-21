# Task 06: `POST /internal/scholarship-programs` Service + Endpoint

## Objective
Implement the atomic upsert service function and the authenticated FastAPI route for
`POST /internal/scholarship-programs`, keyed by `(provider, name)`, idempotent via `content_hash`,
cloned from the `visa_requirements` reference implementation.

## Background
Same template as Task 05, applied to the brand-new `scholarship_programs` table (Task 01) instead of
the pre-existing `program_requirements` table. Because `scholarship_programs` is created fresh with
its unique constraint already in place (unlike `program_requirements`, which needed the Task 02
retrofit), this task has no schema-gap risk — the table is upsert-ready from the moment Task 01 lands.
The one added complexity versus the visa pattern is JSONB serialization for `eligibility`
(`NOT NULL DEFAULT '{}'`), following the same `json.dumps(...)` + `::jsonb` cast pattern
`visa_service.py:21-23` already uses for `requirements`/`proof_of_funds`.

## Scope
- `services/rag/app/services/scholarship_programs_service.py` (new)
- `services/rag/app/api/scholarship_programs.py` (new)
- `services/rag/app/main.py` (add router import + `include_router` call)

## Implementation Steps
- [ ] `scholarship_programs_service.py::upsert_scholarship_program(data: dict) -> dict`:
      - Same atomic-upsert shape as `visa_service.py:7-59`, targeting `scholarship_programs` and its
        columns (`name`, `provider`, `country`, `degree_level`, `award_amount`, `deadline`,
        `eligibility`, `citizenship_eligible`, `min_gpa`, `min_ielts`, `source_url`, `content_hash`).
      - Conflict target: `ON CONFLICT (provider, name) DO UPDATE`, matching the ticket's stated
        upsert key exactly.
      - Serialize `eligibility` via `json.dumps(data.get("eligibility") or {})` before the `::jsonb`
        cast, mirroring `visa_service.py:21`.
      - **Same `last_scraped_at` deviation as Task 05**: the `DO UPDATE SET` clause unconditionally
        advances `last_scraped_at`/`updated_at`, satisfying the ticket's explicit "re-running the same
        payload is idempotent (no duplicate, `last_scraped_at` updated)" acceptance criterion — do not
        copy the visa pattern's hash-gated `WHERE` suppression verbatim.
      - Report `action` as `"inserted"` or `"updated"` via `(xmax = 0)`.
- [ ] `scholarship_programs.py`: `POST /internal/scholarship-programs`, `Security(verify_api_key)`,
      delegates to the service, wraps in `try/except Exception → HTTPException(500)` — identical shape
      to `api/visa.py`.
- [ ] Register the new router in `app/main.py`.

## Expected Files/Modules
- `services/rag/app/services/scholarship_programs_service.py` (new)
- `services/rag/app/api/scholarship_programs.py` (new)
- `services/rag/app/main.py` (edited — 2 lines added, alongside Task 05's 2 lines)

## Dependencies
- Task 01 (`scholarship_programs` table and its `UNIQUE (provider, name)` constraint).
- Task 04 (`ScholarshipProgramUpsertRequest` schema).

## Risks
- **`deadline` type handling in the raw SQL.** `data.get("deadline")` will be a Python `date` object
  (or `None`) after Task 04's schema validation — `asyncpg` handles native `date` params directly, no
  string formatting needed; do not manually stringify it before passing to `conn.fetchrow(...)`.
- **Same `last_scraped_at` deviation risk as Task 05** — copying the visa pattern's suppression clause
  verbatim would violate this ticket's explicit idempotency acceptance criterion.

## Definition of Done
- Calling the service with a brand-new `(provider, name)` key inserts a new row with all fields
  (including `eligibility` as JSONB and `deadline` as a `DATE`) persisted correctly,
  `action="inserted"`.
- Calling it again with the identical payload updates `last_scraped_at`/`updated_at` and returns
  success without creating a duplicate row, `action="updated"`.
- Calling it with a changed `award_amount`/`deadline`/etc. updates those fields plus
  `last_scraped_at`.
- `POST /internal/scholarship-programs` returns `401` without/with-wrong key, `200` with the correct
  key and a valid payload.

## Acceptance Criteria
- Ticket's explicit integration-test wording is satisfied directly: "`POST /internal/scholarship-
  programs` upserts a row; re-running the same payload is idempotent (no duplicate,
  `last_scraped_at` updated)."
- Unit tests mirroring `tests/test_visa.py:73-199`'s structure pass, including a JSONB round-trip
  assertion for `eligibility` and a `date` round-trip assertion for `deadline`.

## Notes for Implementation
- This task and Task 05 are independent of each other (different tables, different files) and can be
  implemented in either order or in parallel — both depend on Task 07 only insofar as adapters
  (Tasks 09–11) need the shared `content_hash` helper to produce the `content_hash` values these
  endpoints receive, not for the endpoints' own logic.
- Do not reuse or subclass `visa_service.py`'s function — copy its pattern into a new, independent
  function. `program_requirements`, `scholarship_programs`, and `visa_requirements` remain three
  separate tables with three separate service functions, consistent with how `documents.py`'s upsert
  is also its own independent function rather than a shared abstraction.

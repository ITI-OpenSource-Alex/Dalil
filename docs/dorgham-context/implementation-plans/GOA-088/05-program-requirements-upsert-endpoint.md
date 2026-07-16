# Task 05: `POST /internal/program-requirements` Service + Endpoint

## Objective
Implement the atomic upsert service function and the authenticated FastAPI route for
`POST /internal/program-requirements`, keyed by `(university, degree_level, country)`, idempotent via
`content_hash`, cloned from the `visa_requirements` reference implementation.

## Background
`app/services/visa_service.py::upsert_visa_requirements` (lines 7-73) already solves exactly this
problem for `visa_requirements`: a single atomic
`INSERT ... ON CONFLICT (country, visa_type, issuing_body) DO UPDATE ... WHERE content_hash IS
DISTINCT FROM EXCLUDED.content_hash RETURNING id, (xmax = 0) AS inserted`, with a documented reason
in its own docstring — it replaced an earlier racy SELECT-then-branch implementation vulnerable to a
TOCTOU unique-constraint violation under concurrent requests. `app/api/visa.py` (9 lines) is the
matching thin-router template: `Security(verify_api_key)`, `request.model_dump()`, delegate to the
service, catch-all `except Exception` → `HTTPException(500)`. Both are directly reusable templates,
not just prior art — this task clones their structure with `program_requirements`'s column set and
conflict key.

## Scope
- `services/rag/app/services/program_requirements_service.py` (new)
- `services/rag/app/api/program_requirements.py` (new)
- `services/rag/app/main.py` (add router import + `include_router` call)

## Implementation Steps
- [ ] `program_requirements_service.py::upsert_program_requirements(data: dict) -> dict`:
      - Same shape as `visa_service.py:7-59`, targeting `program_requirements` and its columns
        (`university`, `country`, `degree_level`, `min_ects`, `min_gpa`, `min_ielts`,
        `required_citizenship`, `min_work_experience`, `source_url`, `content_hash`).
      - Conflict target: `ON CONFLICT (university, degree_level, country) DO UPDATE`.
      - **Deliberate deviation from the visa pattern**: GOA-088's acceptance criteria explicitly
        require `last_scraped_at` to update even when a re-posted payload is idempotent ("no
        duplicate, `last_scraped_at` updated"). The visa pattern's `WHERE content_hash IS DISTINCT
        FROM EXCLUDED.content_hash` clause suppresses the entire `DO UPDATE` (including
        `last_scraped_at`) on an unchanged hash — copying that clause verbatim would fail this
        ticket's own acceptance criterion. Instead: the `DO UPDATE SET` clause should
        unconditionally set `last_scraped_at = NOW()` and `updated_at = NOW()`, while the *other*
        mutable fields (`min_ects`, `min_gpa`, etc.) are set via a `CASE`/`COALESCE` guarded on
        hash-equality, or the row is always fully rewritten (simplest: always `SET` every field to
        `EXCLUDED.<field>`, since rewriting identical values is harmless — the only behavior that
        actually matters for the "idempotent, no duplicate" criterion is the unique-key-based
        `ON CONFLICT`, not further no-op suppression). Prefer the simpler always-rewrite form unless
        profiling shows write amplification is a real concern.
      - Report `action` as `"inserted"` or `"updated"` via `(xmax = 0)`, matching `visa_service.py:62`
        — there is no third `"unchanged"` branch needed here since every conflict now results in a
        real `UPDATE` (of at least `last_scraped_at`), unlike the visa pattern which can suppress the
        update entirely.
- [ ] `program_requirements.py`: `POST /internal/program-requirements`, `Security(verify_api_key)`,
      delegates to the service, wraps in `try/except Exception → HTTPException(500)` — identical shape
      to `api/visa.py`.
- [ ] Register the new router in `app/main.py`, following the existing `visa_router`/
      `documents_router` import + `app.include_router(...)` pattern.

## Expected Files/Modules
- `services/rag/app/services/program_requirements_service.py` (new)
- `services/rag/app/api/program_requirements.py` (new)
- `services/rag/app/main.py` (edited — 2 lines added)

## Dependencies
- Task 02 (migration adding `content_hash`/`source_url`/`last_scraped_at`/`updated_at` and the unique
  constraint — this service cannot function without it).
- Task 03 (`ProgramRequirementsUpsertRequest` schema).

## Risks
- **Copying the visa pattern's `WHERE content_hash IS DISTINCT FROM ...` clause verbatim would violate
  this ticket's own acceptance criterion** (`last_scraped_at` must update even when unchanged) — this
  is the single most important deviation to get right in this task; see Implementation Steps above.
- **Auth omission.** `app/api/documents.py` and `app/api/visa.py` both already apply
  `Security(verify_api_key)` — there is no precedent gap to repeat here (unlike GOA-086, which found
  the visa endpoint initially unauthenticated). Do not skip this.

## Definition of Done
- Calling the service with a brand-new `(university, degree_level, country)` key inserts a new row
  with all fields persisted correctly, `action="inserted"`.
- Calling it again with the same key and the same `content_hash` updates `last_scraped_at` (and
  `updated_at`) but leaves other field values unchanged (they're rewritten to the same values),
  `action="updated"`.
- Calling it again with the same key and a different `content_hash` updates all mutable fields plus
  `last_scraped_at`, `action="updated"`.
- Repeated calls with the same key never violate the unique constraint or raise unhandled errors.
- `POST /internal/program-requirements` returns `401` without/with-wrong `X-Internal-Api-Key`, `200`
  with the correct key and a valid payload.

## Acceptance Criteria
- Ticket's own acceptance wording — "upsert, keyed by university + degree_level + country" and
  "idempotent via content_hash" — is satisfied: repeated identical POSTs never create duplicate rows,
  and each POST advances `last_scraped_at`.
- Unit tests mirroring `tests/test_visa.py:73-199`'s structure (mocked `asyncpg` pool for the service,
  `TestClient` for the endpoint) pass.

## Notes for Implementation
- This task does not change GOA-086's `visa_service.py` in any way — the `last_scraped_at` semantics
  deviation is local to `program_requirements_service.py` only, driven by GOA-088's own acceptance
  criteria, not a redesign of the visa pattern.
- `get_program_requirements()` (`app/services/scoring.py:24-44`) selects a fixed, narrower column list
  than the full table — confirm (do not assume) that adding new columns here doesn't require touching
  that function; it explicitly names its `SELECT` columns, so it won't break, but it also won't expose
  `content_hash`/`source_url`/`last_scraped_at` to the gates code, which is correct (those are
  ingestion metadata, not gating inputs).

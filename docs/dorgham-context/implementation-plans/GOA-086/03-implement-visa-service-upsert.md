# Task 03: Implement Real Upsert Logic in `visa_service.py`

## Goal
Replace the no-op stub in `upsert_visa_requirements` with a real `asyncpg`
`INSERT ... ON CONFLICT (country, visa_type, issuing_body) DO UPDATE` against the
`visa_requirements` table.

## Why this task exists
`services/rag/app/services/visa_service.py::upsert_visa_requirements` currently returns
`{"status": "success", "message": "Stub processed successfully"}` and never touches the database.
This is the core persistence logic the entire ticket depends on — nothing else in this plan matters
if this function doesn't actually write rows.

## Prerequisites
- Task 01 (the `egyptian_specific` column must exist before this function can write to it).
- Task 02 (the schema must expose validated `egyptian_specific` and structured `proof_of_funds`
  fields for this function to persist).

## Scope
Only `services/rag/app/services/visa_service.py`. No changes to `app/api/visa.py` in this task
(routing/auth is Task 04; this task only changes what the route calls).

## Implementation Steps
- [ ] Import the shared `app.core.database.db` connection pool, matching the pattern in
      `app/api/documents.py::upsert_documents`.
- [ ] Build a parameterized upsert statement covering all `visa_requirements` columns: `id` (or let
      the DB default generate it), `country`, `visa_type`, `issuing_body`, `source_url`,
      `egyptian_specific`, `requirements`, `proof_of_funds`, `processing_days_min`,
      `processing_days_max`, `notes`, `content_hash`, `last_scraped_at`.
- [ ] Use `ON CONFLICT (country, visa_type, issuing_body) DO UPDATE SET ...` for all mutable columns.
- [ ] Add content-hash-aware skip logic: only update the mutable fields and `last_scraped_at` when
      the incoming `content_hash` differs from the stored value for that key (e.g. via a
      `WHERE visa_requirements.content_hash IS DISTINCT FROM EXCLUDED.content_hash` clause on the
      `DO UPDATE`, or an explicit `SELECT` first) — this avoids needless `last_scraped_at` churn on
      unchanged content, matching the idempotency approach used elsewhere in ingestion (GOA-010).
- [ ] Serialize `requirements` and `proof_of_funds` to JSONB — follow whatever JSON-column pattern
      already exists in `app/core/database.py`/`documents.py`, or establish an equivalent
      (`json.dumps` + `::jsonb` cast, or asyncpg's native dict handling if configured) consistently.
- [ ] Wrap the write in `async with db.pool.acquire() as conn: async with conn.transaction(): ...`,
      matching `documents.py::upsert_documents`.
- [ ] Return a real result dict (e.g. `{"status": "success", "id": ..., "action": "inserted" |
      "updated" | "unchanged"}`) instead of the stub's hardcoded message.
- [ ] Leave the existing `try/except` → `HTTPException(500)` wrapper in `app/api/visa.py` as-is (no
      change needed there for this task).

## Files Expected to Change
- `services/rag/app/services/visa_service.py`

## Acceptance Criteria
- Calling `upsert_visa_requirements` with a brand-new `(country, visa_type, issuing_body)` key
  inserts a new row with all fields correctly persisted.
- Calling it again with the same key and the same `content_hash` does not change any mutable field
  or `last_scraped_at`, but still returns a success result.
- Calling it again with the same key and a *different* `content_hash` updates the mutable fields and
  `last_scraped_at`.
- Repeated calls with the same key never violate the unique constraint or raise unhandled errors.

## Testing
- Integration tests in `services/rag/tests/test_visa.py` against a real/test Postgres instance
  (matching whatever fixture/setup pattern `test_gates.py`/`test_query.py` already use):
  - Insert a new row, assert all fields (including `egyptian_specific`, `requirements`,
    `proof_of_funds` JSONB) round-trip correctly.
  - Call twice with an identical `content_hash`; assert `last_scraped_at` is unchanged on the second
    call.
  - Call with a different `content_hash`; assert fields and `last_scraped_at` update.
  - Call twice in immediate succession with the same key (simulating the within-a-run duplicate-key
    edge case from the main plan) and assert no constraint violation.

## Notes
- This task does **not** add authentication to the endpoint — that is Task 04, done independently.
- The 9 adapter tasks (07–15) and the wiring task (16) depend on this function actually persisting
  data — integration testing in Task 18 assumes this task is complete.

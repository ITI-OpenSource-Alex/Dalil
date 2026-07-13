# Task 16: Wire the 9 Adapters and Dual-Write Pipeline into Both Ingestion Entry Points

## Goal
Register all 9 new Egypt adapters in both `handler.py::fetch_all_adapters` and
`app/services/run_orchestrator.py::run_ingestion`, and add the dual-write post-processing (pop the
optional `visa_requirements` key off each document dict, upsert each record independently via
`client.upsert_visa_requirement`, isolate failures on each path, extend the completion report).

## Why this task exists
The 9 adapters built in Tasks 07–15 don't do anything real until they're part of an actual ingestion
run. This task is where GOA-086's core acceptance criterion — "ingestion of a source both upserts a
`visa_requirements` row and creates `documents` chunks" — actually happens end-to-end, and where the
dual-write consistency strategy (independent, idempotent, isolated writes; no distributed
transaction) gets implemented.

## Prerequisites
- Tasks 07–15 (all 9 adapters must exist and be importable).
- Task 05 (rate-limiting base class changes, already a dependency of 07–15).
- Task 06 (`client.py::upsert_visa_requirement`).
- Tasks 01–04 (RAG-side migration, schema, upsert logic, and auth) — needed for this task's own
  integration testing to be meaningful against a real endpoint, though the wiring code itself only
  needs Task 06's client function to exist to compile.

## Scope
- `services/ingestion/handler.py`
- `services/ingestion/app/services/run_orchestrator.py`

No RAG-service-side code changes in this task (that's Tasks 01–04, already done).

## Implementation Steps
- [ ] Import the 9 new adapter classes into both `handler.py` and `run_orchestrator.py`.
- [ ] Add all 9 to the hardcoded adapter list in `fetch_all_adapters()` (`handler.py`) and in
      `run_ingestion()`'s `adapters = [...]` (`run_orchestrator.py`) — matching current practice of
      duplicating the list in both places (per main plan Question #3's recommendation).
- [ ] In each file's per-document processing loop (where `doc_dict`s are converted into
      `langchain_core.documents.Document` objects), add:
      `visa_records = doc_dict.pop("visa_requirements", [])` before the `Document(...)`
      construction, and accumulate all `visa_records` across the whole run into a single list.
- [ ] After (or interleaved with) the existing document chunk/embed/upsert flow, iterate the
      accumulated `visa_records` and call `client.upsert_visa_requirement(record)` for each, each
      call wrapped in its own `try/except` so that one record's failure does not abort processing of
      the remaining records or the document-chunk pipeline.
- [ ] Extend the completion report dict in both files with `visa_requirements_upserted` and
      `visa_requirements_failed` counters, incremented per successful/failed call.
- [ ] Confirm the existing per-adapter isolation in `run_orchestrator.py`
      (`asyncio.gather(..., return_exceptions=True)`) wraps the 9 new adapters identically to the
      existing 6 — no special-casing needed, but verify it explicitly since this is where a broken
      Playwright adapter (Tasks 11/12) would otherwise be able to take down the whole run.
- [ ] Update structured completion logging (both files already log a completion summary) to include
      the new visa counters.

## Files Expected to Change
- `services/ingestion/handler.py`
- `services/ingestion/app/services/run_orchestrator.py`

## Acceptance Criteria
- Running the full pipeline (fixture-mode) processes all 15 adapters (6 pre-existing + 9 new).
- Each Egypt adapter's structured `visa_requirements` entries are POSTed individually to the RAG
  service via `client.upsert_visa_requirement`.
- A simulated failure in the visa-upsert call for one record does not prevent other records, other
  adapters, or the document-chunk pipeline from completing.
- A simulated failure in the document-chunk upsert for one adapter does not prevent that adapter's
  visa records from being upserted (or vice versa).
- The completion report/log includes `visa_requirements_upserted`/`visa_requirements_failed` counts
  that accurately reflect what happened during the run.

## Testing
- Integration tests extending the existing patterns in `tests/test_orchestrator.py` /
  `tests/test_ingestion.py`:
  - Mock all 9 new adapters' `scrape()` to return fixture output including populated
    `visa_requirements`; assert `client.upsert_visa_requirement` is called once per accumulated
    record across the whole run.
  - Force an exception from `client.upsert_visa_requirement` on one call; assert subsequent calls
    still happen and the document pipeline still completes; assert the failure is reflected in the
    completion report's `visa_requirements_failed` counter.
  - Force an exception in the document-chunk upsert path for one adapter; assert that adapter's
    visa records are still attempted/upserted.
  - Confirm the existing 6 adapters' behavior in both entry points is unaffected (regression check).

## Notes
- This task is the concrete implementation of the main plan's "dual-write consistency strategy (no
  2PC/saga)" — recovery from a partial failure is simply re-running the adapter on the next
  scheduled/manual ingestion pass, relying on both sides' idempotency (unique key on
  `visa_requirements`, deterministic UUID v5 on document chunks).
- This task is a hard prerequisite for Task 18 (integration and regression testing).

# Task 14: Structured Logging + Error Handling for the New Dual-Write Paths

## Objective
Ensure the new `program_requirements`/`scholarship_programs` dual-write paths (adapters, client
functions, orchestrator wiring, RAG endpoints) produce structured logs and error responses consistent
with the existing GOA-086 visa path and the codebase's `structlog` conventions, with no silent
failures anywhere in the chain.

## Background
This task doesn't introduce new mechanisms — it consolidates and verifies the logging/error-handling
touch points already specified piecemeal across Tasks 05, 06, 08, and 12, using the exact patterns
already present in the codebase:

- **RAG service**: `structlog.get_logger(...)` per module (e.g. `"rag_service.api.visa"` in
  `app/api/visa.py:9`), broad `except Exception` at the route boundary logging the error and returning
  `HTTPException(500, "Internal Processing Error")` (`app/api/visa.py:17-19`).
- **Ingestion service**: Python stdlib `logging.getLogger(...)` in `client.py` (not `structlog` — this
  module uses the older stdlib logger, e.g. `logger = logging.getLogger('ingestion_worker.client')` at
  `client.py:5`), `structlog` in `run_orchestrator.py` (`logger = structlog.get_logger(__name__)`,
  `run_orchestrator.py:26`). Both conventions coexist in the ingestion service today — this task
  follows whichever convention already exists in each file being touched, rather than unifying them
  (unifying stdlib logging and structlog across the ingestion service is out of scope for GOA-088).

This task exists to make explicit what "consistent logging/error handling" means for each of the 4
new touch points, since it's easy for a piecemeal implementation (Tasks 05/06/08/12, each done by a
possibly different session/PR) to drift into 4 slightly different logging styles if not called out as
its own checklist.

## Scope
Cross-cutting verification/consistency pass across:
- `services/rag/app/api/program_requirements.py`, `app/api/scholarship_programs.py` (Tasks 05/06)
- `services/rag/app/services/program_requirements_service.py`, `app/services/scholarship_programs_service.py`
  (Tasks 05/06)
- `services/ingestion/client.py` (Task 08)
- `services/ingestion/app/services/run_orchestrator.py` (Task 12)

No new files — this task's changes are folded into the files Tasks 05/06/08/12 already touch. It is
broken out as its own task here so logging/error-handling consistency is explicitly reviewed, not
because it is a separate code change.

## Implementation Steps
- [ ] RAG endpoints (`api/program_requirements.py`, `api/scholarship_programs.py`): use
      `structlog.get_logger("rag_service.api.program_requirements")` /
      `"rag_service.api.scholarship_programs"`, matching `api/visa.py:9`'s naming convention; log a
      single `logger.error(...)` call inside the route's `except Exception` block before raising
      `HTTPException(500, "Internal Processing Error")`, matching `api/visa.py:17-19` verbatim.
- [ ] RAG services (`services/program_requirements_service.py`, `services/scholarship_programs_service.py`):
      no logging inside the service function itself, matching `visa_service.py`'s convention (it lets
      exceptions propagate to the route's `except Exception` handler rather than logging at both
      layers) — do not double-log the same error at both the service and route layers.
- [ ] Ingestion `client.py` additions (`upsert_program_requirement`, `upsert_scholarship_program`):
      use the existing module-level `logger = logging.getLogger('ingestion_worker.client')`, matching
      `upsert_visa_requirement`'s exact log-message shape (`logger.info("Upserting ... to RAG service at
      %s", url)` on attempt, `logger.info("Successfully upserted ...")` on success,
      `logger.error("RAG ...endpoint failed with status %d: %s", ...)` on non-200,
      `logger.error("Failed to connect to RAG ...endpoint: %s", str(e))` on connection failure, then
      re-raise in both failure cases — matching `client.py:51-63`'s pattern exactly, including that
      exceptions propagate to the caller (`run_orchestrator.py`) rather than being swallowed here).
- [ ] `run_orchestrator.py` (Task 12's wiring): use the existing `structlog` logger
      (`logger = structlog.get_logger(__name__)`, already at the top of the file), with
      `logger.error("program_requirement_upsert_failed", source=source_name, error=str(e))` /
      `logger.error("scholarship_program_upsert_failed", source=source_name, error=str(e))` inside
      each per-record `except` block, matching the existing
      `logger.error("visa_requirement_upsert_failed", source=source_name, issuing_body=..., error=str(e))`
      shape (`run_orchestrator.py:97-102`) — same event-name-as-first-positional-arg convention, same
      structured kwargs style.
- [ ] Extend the final `logger.info("ingestion_run_completed", ...)` call
      (`run_orchestrator.py:136-144`) with the 4 new counts (Task 12), keeping the existing flat-field
      structured-log style (no nested objects).
- [ ] Confirm no exception anywhere in the new paths is caught and silently discarded without either a
      log line or a re-raise — every new `except` block must do at least one of: log + re-raise, or
      log + increment a failure counter (the latter only at the per-record isolation points in
      `run_orchestrator.py`, never at the `client.py` function level, which always re-raises).

## Expected Files/Modules
- Same files as Tasks 05, 06, 08, 12 — no new files.

## Dependencies
- Tasks 05, 06, 08, 12 (this task is a consistency/completeness pass over their logging/error-handling
  code, not independent work — in practice it should be applied within each of those tasks' own PRs
  rather than as a separate late-stage pass, but is documented here as its own checklist so it isn't
  forgotten or done inconsistently across the 4 tasks).

## Risks
- **Drift between the two logging conventions.** Ingestion mixes stdlib `logging` (`client.py`) and
  `structlog` (`run_orchestrator.py`) — using the wrong one in a new function (e.g. `structlog`-style
  keyword args passed to a stdlib `logger.error(...)` call, which does not support them the same way)
  would silently produce malformed log output rather than raising an error. Follow each file's existing
  convention exactly, do not introduce a third style.
- **Double-logging.** If a service-layer function logs an error and the route layer also logs the same
  exception, log volume doubles for every failure with no added signal — verify only one layer logs
  per new touch point, matching the existing visa pattern where only the route layer logs.
- **Swallowed exceptions.** The riskiest failure mode for this ticket's dual-write guarantee is a
  structured-row upsert failing *silently* (no log, no counter increment, no re-raise) — this would
  make data gaps invisible. Every new `except` block must be checked against this specifically.

## Definition of Done
- Every new logging call site follows its containing file's existing logging library and message-shape
  convention exactly (verified by direct comparison against the equivalent existing visa/documents call
  site, not by independent judgment).
- No exception in any new code path is caught without either a log line or a re-raise.
- The final ingestion-run log line includes all 4 new structured-row counts.

## Acceptance Criteria
- A forced failure at each of the 4 new touch points (RAG endpoint, RAG service, `client.py` function,
  orchestrator per-record loop) produces exactly one log line at the correct severity, with either
  propagation (re-raise) or isolation (counter increment + continue) as specified above — verified in
  Task 17's failure-scenario tests.

## Notes for Implementation
- This task intentionally does not attempt to unify the ingestion service's two coexisting logging
  conventions (stdlib `logging` in `client.py` vs. `structlog` elsewhere) — that is a larger, unrelated
  cleanup outside GOA-088's scope.
- This task also does not add retry/backoff to `client.py`'s new functions — that is explicitly called
  out as pre-existing technical debt in the master plan's Future Improvements, not something to
  introduce here under the guise of "error handling."

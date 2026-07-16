# Task 18: Integration and Regression Testing

## Goal
Execute GOA-086's end-to-end Definition-of-Done integration checks across all components built in
Tasks 01–17, plus a full regression pass confirming the 6 pre-existing (non-Egypt) adapters and
their tests are unaffected.

## Why this task exists
Tasks 01–17 are each unit-tested in isolation. GOA-086's actual acceptance criteria — "run all 9
adapters," "verify upsert behavior," "verify `/internal/visa-requirements`," "verify an APS
certificate query," "verify a blocked account query," "verify FAQ cache hit" — are cross-cutting and
can only be meaningfully exercised once every earlier task is complete and wired together.

## Prerequisites
- Tasks 01–17 all complete.

## Scope
New integration test file(s) in `services/rag/tests/` and `services/ingestion/tests/`. No new
production/application code is expected in this task — if a check fails, the fix belongs in the
originating task (see Notes), not patched here.

## Implementation Steps
- [ ] Run all 9 Egypt adapters (fixture-mode) through the wired pipeline (Task 16) end-to-end;
      assert both document chunks and `visa_requirements` row(s) land correctly for each.
- [ ] Hit `POST /internal/visa-requirements` directly (via HTTP, not just the service function) with
      a valid payload and a valid `X-Internal-Api-Key`; assert `200` and a persisted row — this
      exercises Tasks 02/03/04 together through the real route, not just their individual unit
      tests.
- [ ] Exercise a `/query` call expected to be answerable via APS-certificate-related document
      content (from Task 08); assert the answer references APS content and cites a source
      (`source_url`).
- [ ] Exercise a `/query` call expected to be answerable via blocked-account/Sperrkonto content (from
      Task 12); same assertions.
- [ ] Dual-write partial-failure test: mock the document-chunk upsert to fail for one adapter while
      its visa upsert succeeds (and a separate case, vice versa); assert the run completes, the
      completion report/log reflects the partial failure via the `visa_requirements_failed` /
      document-equivalent counters (Task 16), and neither failure blocks other adapters.
- [ ] **FAQ cache-hit**: do not write a fake-passing test. Add an explicitly skipped/pending test (or
      a clearly commented placeholder) referencing the GOA-045 gap, so the gap remains visible in CI
      output rather than silently disappearing.
- [ ] Regression: run the full existing `services/ingestion/tests/test_adapters.py` and
      `services/rag/tests/` suites unmodified; confirm 100% pass, verifying that Task 05's rate-limit
      base-class change and Tasks 07–15's additive use of the optional `visa_requirements` key did
      not break any of the 6 pre-existing adapters.

## Files Expected to Change
- New test files, e.g. `services/rag/tests/test_visa_integration.py`,
  `services/ingestion/tests/test_egypt_ingestion_e2e.py` (exact names at implementer's discretion).
- No production code changes expected. If this task uncovers a bug, open/reopen the relevant earlier
  task (e.g. an adapter parsing bug goes back to its Task 07–15) rather than patching ad hoc here, to
  keep task boundaries clean for review.

## Acceptance Criteria
- All listed integration checks pass, except the explicitly-deferred FAQ cache-hit check (marked
  skipped/pending, not silently omitted).
- The full regression suite (pre-existing + newly added tests) is green.
- GOA-086's Definition of Done is satisfied, modulo the documented FAQ/GOA-045 gap, which is called
  out explicitly rather than hidden.

## Testing
This task **is** the testing task — see Implementation Steps above for the full list of checks to
run.

## Notes
- If any integration check fails, fix the root cause in its originating task rather than here — this
  keeps each numbered task's diff reviewable in isolation.
- The FAQ cache-hit gap should be raised with the ticket owner per the main plan's Question #1
  (descope permanently to GOA-045, vs. implement a minimal FAQ pre-check as part of this ticket). If
  the team chooses the latter, that is new scope beyond this 18-task breakdown and should be planned
  as its own follow-up task rather than squeezed into this one.
- This is the last task in the sequence — once it passes, GOA-086 (as scoped by this breakdown) is
  complete.

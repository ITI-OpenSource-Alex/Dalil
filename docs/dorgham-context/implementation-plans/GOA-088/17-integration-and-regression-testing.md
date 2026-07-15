# Task 17: Integration and Regression Testing

## Objective
Execute GOA-088's end-to-end Definition-of-Done checks across everything built in Tasks 01–16, plus a
full regression pass confirming the pre-existing unstructured ingestion pipeline (all adapters, GOA-086
visa dual-write, GOA-012 gates) is unaffected.

## Background
Tasks 01–16 are each unit-tested in isolation. GOA-088's actual acceptance criteria — "an ingestion run
populates both tables and writes chunked documents from the same sources," "`POST
/internal/scholarship-programs` upserts a row... idempotent," "GOA-012 hard gate blocks a profile with
insufficient ECTS," "GOA-024 diff query returns rows... in the last 24 hours" — are cross-cutting and
can only be meaningfully exercised once every earlier task is complete and wired together. This mirrors
GOA-086's own final integration task (`GOA-086/18-integration-and-regression-testing.md`), applied to
GOA-088's smaller (3-adapter, 2-table) scope.

## Scope
New integration test file(s) in `services/rag/tests/` and `services/ingestion/tests/`. **No new
production/application code is expected in this task** — if a check fails, the fix belongs in the
originating task (Tasks 01–16), not patched here.

## Implementation Steps
- [ ] Run `MastersPortalAdapter`, `DAADAdapter`, and `CheveningAdapter` (fixture-mode) through the wired
      pipeline (Task 12) end-to-end; assert both document chunks and the correct structured table
      (`program_requirements` for MastersPortal, `scholarship_programs` for DAAD/Chevening) receive
      row(s) for each.
- [ ] Hit `POST /internal/program-requirements` and `POST /internal/scholarship-programs` directly (via
      HTTP, not just the service function) with valid payloads and a valid `X-Internal-Api-Key`; assert
      `200` and persisted rows — exercising Tasks 03/05 and 04/06 together through the real routes.
- [ ] Idempotency check: re-POST an identical `scholarship_programs` payload; assert no duplicate row
      (same `id` returned) and `last_scraped_at` has advanced — the ticket's explicit wording.
- [ ] Re-run Task 15's GOA-012 hard-gate verification as part of this full suite (not just in
      isolation), confirming it still passes once all other tasks are wired together.
- [ ] Re-run Task 16's GOA-024-shaped diff-query verification as part of this full suite.
- [ ] Dual-write partial-failure test: mock the chunk-document upsert to fail for one adapter while its
      structured upsert succeeds (and a separate case, vice versa); assert the run completes, the
      completion report/log reflects the partial failure via the Task 12/13 counters, and neither
      failure blocks the other adapters or paths.
- [ ] Regression: run the full existing `services/ingestion/tests/test_adapters.py`,
      `services/ingestion/tests/test_orchestrator.py`, `services/ingestion/tests/test_client.py`, and
      `services/rag/tests/` suites (including `test_visa.py`, `test_visa_integration.py`,
      `test_gates.py`) unmodified; confirm 100% pass, verifying that Tasks 07's content-hash-helper
      extraction and Tasks 09–12's additive changes did not break GOA-086's visa dual-write or any
      pre-existing adapter.
- [ ] Confirm the 3 pre-existing `program_requirements` seed rows
      (`008_update_program_requirements.sql`) are still present and unaltered after Task 02's migration
      and after a full ingestion run (i.e. ingestion upserts new/updated rows but never deletes
      existing ones it didn't touch).

## Expected Files/Modules
- New test files, e.g. `services/rag/tests/test_structured_ingestion_integration.py`,
  `services/ingestion/tests/test_structured_ingestion_e2e.py` (exact names at implementer's
  discretion).
- No production code changes expected. If this task uncovers a bug, open/reopen the relevant earlier
  task (e.g. an adapter parsing bug goes back to Task 09/10/11) rather than patching ad hoc here, to
  keep task boundaries clean for review.

## Dependencies
- Tasks 01–16 all complete.

## Risks
- **Masking a real bug as a "test-only" fix.** If an integration check fails because of a genuine
  defect in an earlier task's implementation (not a test-setup issue), the fix belongs in that task's
  files, not as a workaround inside this task's test code.
- **Flaky fixture-based network mocking.** All 3 adapters' integration coverage must run against
  fixture HTML, not live sites, consistent with GOA-086's same caution — live-scrape verification is a
  separate manual step, not part of this task's automated suite.
- **Test ordering/isolation.** Tests inserting rows into `program_requirements`/`scholarship_programs`
  must not leave state that causes Task 15/16's tests (or each other) to become order-dependent —
  use distinct, clearly-fixture-tagged values (e.g. a distinguishable `provider`/`university` naming
  convention for test data) to avoid colliding with the 3 real seed rows or with data left by other
  test runs.

## Definition of Done
- All listed integration checks pass.
- The full regression suite (pre-existing + newly added tests) is green.
- GOA-088's Definition of Done, as stated in its acceptance criteria, is fully satisfied — with the
  explicit caveats documented in the master plan (GOA-024's diff query verified at the data level only,
  since no GOA-024 service exists; `notifications_sent` untouched, since it doesn't exist).

## Acceptance Criteria
- Every acceptance-criteria bullet in the master plan's "Acceptance Criteria (from ticket, for
  reference)" section has a corresponding passing test, or an explicit, visible note in this task's
  test output explaining why it is satisfied at a different level (as with the GOA-024 diff query).
- No pre-existing test (ingestion or RAG service) regresses.

## Notes for Implementation
- If any integration check fails, fix the root cause in its originating task rather than here — this
  keeps each numbered task's diff reviewable in isolation, matching GOA-086's own final-task
  convention.
- This is the last task in the GOA-088 sequence — once it passes, GOA-088 (as scoped by this 17-task
  breakdown) is complete, modulo the explicitly-documented deferred/out-of-scope items (LLM extraction
  fast-follow, retry/backoff technical debt, GOA-024/`notifications_sent` future work) captured in the
  master plan's Future Improvements section.

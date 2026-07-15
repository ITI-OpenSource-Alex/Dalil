# Task 16: Verify the GOA-024-Shaped Diff Query at the SQL/Data Level

## Objective
Confirm that `scholarship_programs.last_scraped_at` behaves correctly for a "rows updated in the last
24 hours" query — the shape a future GOA-024 diff engine will need — without building any GOA-024
service, worker, or notification logic.

## Background
GOA-088's ticket text describes GOA-024 (Scholarship matcher) as querying "ScholarshipProgram records
updated in the last 24 hours" and states that its "diff query targets
`scholarship_programs.last_scraped_at`." A repository-wide search confirms **GOA-024 does not exist as
code anywhere** — no ticket detail file, no service, no `ScholarshipProgram` model, no diff-engine
logic, no `/internal` endpoint for it. It is only a one-line row in the master ticket table and
forward-looking prose inside GOA-088's own ticket. **This task does not build GOA-024.** Its only job
is to prove, at the data/SQL level, that the table this ticket creates (Task 01) and populates
(Tasks 10–12) supports the query shape a future GOA-024 would need — satisfying GOA-088's own stated
acceptance criterion ("GOA-024 diff query returns `scholarship_programs` rows with `last_scraped_at`
in the last 24 hours") without inventing a consuming service that doesn't exist yet.

Similarly, GOA-088's ticket text notes that `notifications_sent.program_id` should eventually point at
`scholarship_programs.id` rather than `program_requirements.id`. **`notifications_sent` does not exist
in the repository at all** (confirmed by repository-wide search — no migration, no model, no code).
This task takes no action on it beyond documenting the intended FK for whichever future ticket creates
that table (already captured in the master plan's Context section) — GOA-088 does not create, alter,
or migrate `notifications_sent`.

## Scope
New integration test(s) / a direct SQL verification only. **No GOA-024 service code, no
`notifications_sent` migration, no new endpoints.**

## Implementation Steps
- [ ] Using Task 06's upsert endpoint, insert several `scholarship_programs` rows at known, varying
      `last_scraped_at` timestamps: some within the last 24 hours (fresh upserts, which set
      `last_scraped_at = NOW()` per Task 06's design), and at least one artificially backdated beyond
      24 hours (inserted via a direct SQL statement in the test setup, since the upsert endpoint itself
      always sets `last_scraped_at = NOW()` and cannot produce an old timestamp through normal use).
- [ ] Run the query a future GOA-024 diff engine would use:
      `SELECT * FROM scholarship_programs WHERE last_scraped_at > NOW() - INTERVAL '24 hours'`.
- [ ] Assert the query returns exactly the freshly-upserted rows and excludes the backdated one.
- [ ] Document (as a comment in the test file, or in this task's own notes) that this query shape is
      what a future GOA-024 implementation should use — this is guidance for that future ticket, not a
      commitment this ticket is fulfilling on GOA-024's behalf.

## Expected Files/Modules
- New test file, e.g. `services/rag/tests/test_scholarship_programs_diff_query.py` (exact name at
  implementer's discretion — no production code files expected to change).

## Dependencies
- Task 06 (`scholarship_programs` upsert endpoint/service) — needed to produce rows with realistic
  `last_scraped_at` values through the actual upsert path.

## Risks
- **Scope creep into building GOA-024.** It may be tempting to add a minimal `/internal/scholarship-
  programs/recent` endpoint or a stub diff-engine function "since we're already here." Do not — GOA-024
  has no ticket detail file, no defined notification-trigger behavior, and no owner assignment visible
  in this repository; building even a minimal version of it is out-of-scope speculative work that
  should go through its own ticket, not be absorbed into GOA-088's 3-point sizing.
- **`notifications_sent` scope creep.** Similarly, do not create a `notifications_sent` table or FK
  "to save the future ticket some work" — that decision (schema shape, FK target, whether it lives in
  `rag_db` or a separate notifications-service database) belongs to whichever ticket actually
  implements notifications, not to GOA-088.
- **Timestamp precision/timezone handling.** `last_scraped_at TIMESTAMP DEFAULT NOW()` (no timezone) —
  confirm the test's "24 hours ago" boundary comparison uses the same timezone assumption as the
  database server (`NOW()`), not the test runner's local timezone, to avoid a flaky boundary condition.

## Definition of Done
- A direct SQL query for `scholarship_programs` rows with `last_scraped_at` in the last 24 hours
  correctly includes freshly-upserted rows and excludes older ones.
- No GOA-024 service, worker, endpoint, or notification code is created.
- No `notifications_sent` table, migration, or FK is created.

## Acceptance Criteria
- Ticket's explicit acceptance criterion is satisfied at the data level: "GOA-024 diff query returns
  `scholarship_programs` rows with `last_scraped_at` in the last 24 hours" — verified by a direct query
  against real data, not by a GOA-024 service that doesn't exist.

## Notes for Implementation
- This task exists specifically to prevent two failure modes: (a) silently skipping this acceptance
  criterion because "GOA-024 doesn't exist so we can't test it," and (b) over-delivering by building
  speculative GOA-024 infrastructure that isn't requested, isn't specified, and would need its own
  design review. The data-level verification here threads that needle.
- If/when GOA-024 is eventually scoped as its own ticket, this task's test and its documented query
  shape are a reasonable starting reference for that ticket's own implementation plan — but this task
  does not attempt to anticipate GOA-024's full design (e.g. how it determines *which* rows to notify
  about beyond the 24-hour window, deduplication, notification delivery mechanism).

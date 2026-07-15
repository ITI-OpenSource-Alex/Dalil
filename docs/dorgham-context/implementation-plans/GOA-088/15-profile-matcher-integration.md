# Task 15: Verify GOA-012 Hard Gates Against Real Ingested `program_requirements` Data

## Objective
Confirm — via a targeted integration test, not new production code — that GOA-012's existing hard-gate
logic correctly reads and evaluates `program_requirements` rows populated by this ticket's ingestion
path, satisfying the ticket's explicit acceptance criterion without modifying GOA-012 itself.

## Background
GOA-012 (Profile Matcher) is **already fully implemented** and already reads `program_requirements`
correctly:

- `services/rag/app/services/scoring.py:24-44::get_program_requirements(program_id)` runs
  `SELECT id, min_ects, degree_level, required_citizenship, min_ielts, min_gpa, min_work_experience
  FROM program_requirements WHERE id = $1`.
- `services/rag/app/services/gates.py::check_hard_gates(profile, program)` evaluates `min_ects`,
  `degree_level`, and `required_citizenship` against a `UserProfile`, returning a `GateResult`.
- `services/rag/app/api/scoring.py:18-23::match_profile` iterates every row's `id` from
  `program_requirements` and scores each.

**No GOA-012 code changes are in scope for GOA-088.** The gap this ticket closes is entirely on the
*data* side: today `program_requirements` has only 3 hand-seeded rows
(`008_update_program_requirements.sql`); after Tasks 01–12 land, `MastersPortalAdapter`'s ingestion
output populates real rows into the same table the existing gates code already queries correctly. This
task is a verification/integration-testing task confirming that connection works end-to-end, not an
implementation task against GOA-012 itself.

## Scope
New integration test(s) only. **No production code changes** — if this task's testing uncovers a bug
in `gates.py`/`scoring.py`, the fix belongs to a GOA-012 bug-fix task, not folded into GOA-088's scope
silently.

## Implementation Steps
- [ ] Using Task 05's upsert endpoint (or the underlying service function directly), insert a real
      `program_requirements` row with a known `min_ects` value (e.g. 120) via the same code path
      `MastersPortalAdapter`'s ingestion would use in production (Task 09 → Task 08 →
      `POST /internal/program-requirements`).
- [ ] Construct a `UserProfile` (`app/schemas/scoring.py:5-17`) with `ects` below that threshold.
- [ ] Call `check_hard_gates(profile, program)` (or exercise it via `POST /scoring/score`,
      `app/api/scoring.py:13-15`) and assert `GateResult.passed is False`,
      `GateResult.gateType == "ects"`.
- [ ] Repeat with a profile meeting the ECTS threshold and assert the gate passes (assuming
      `degree_level`/`required_citizenship` also match or are `None` on the row).
- [ ] Confirm `match_profile` (`POST /scoring/match`) correctly includes the newly-ingested program's
      `id` in its `SELECT id FROM program_requirements` sweep and returns a scored result for it.

## Expected Files/Modules
- New test file, e.g. `services/rag/tests/test_program_requirements_gates_integration.py` (exact name
  at implementer's discretion — no production code files expected to change).

## Dependencies
- Task 05 (`program_requirements` upsert endpoint/service) — needed to seed a real row through the
  actual ingestion-shaped code path rather than a raw SQL insert, so this test exercises the same data
  path production ingestion will use.
- Task 09 (optional but preferred) — running this test against `MastersPortalAdapter`'s actual
  extraction output (via a fixture) is a stronger proof than a hand-constructed payload, though a
  hand-constructed payload posted through Task 05's endpoint is sufficient to satisfy the ticket's
  literal acceptance criterion.

## Risks
- **Scope creep into GOA-012 changes.** It is tempting, if this test reveals gate-logic edge cases
  (e.g. how `gates.py` handles a `program_requirements` row with `NULL` `min_ects`), to "fix" GOA-012
  code as part of this task. Resist this — GOA-012 is a separately-owned, already-implemented ticket;
  any real bug found here should be filed and fixed as its own change, not silently absorbed into
  GOA-088's diff.
- **Test data collision with the 3 existing seed rows.** Ensure the test's inserted/upserted row uses a
  `(university, degree_level, country)` combination that doesn't collide with
  `008_update_program_requirements.sql`'s 3 seed rows, to keep the test deterministic and independent
  of seed-data presence/absence in the target test database.

## Definition of Done
- A `program_requirements` row inserted via the real ingestion-shaped upsert path is correctly read by
  `get_program_requirements` and correctly evaluated by `check_hard_gates`.
- A profile with insufficient ECTS against that row is blocked (`passed=False`, `gateType="ects"`).
- A profile meeting the row's requirements passes the ECTS gate.
- No changes to `gates.py`, `scoring.py`, or any other GOA-012 file.

## Acceptance Criteria
- Ticket's explicit acceptance criterion is satisfied verbatim: "GOA-012 hard gate reads a real
  `program_requirements` row and blocks a profile with insufficient ECTS."

## Notes for Implementation
- This task is deliberately thin — its entire purpose is closing the loop between "ingestion writes
  real data" (Tasks 01–12) and "GOA-012 already reads that data correctly" (pre-existing), not adding
  new capability to either side.
- If `required_citizenship`/`degree_level` gating also needs verification for completeness, extend this
  same test file rather than creating a separate one — keep GOA-012-integration tests co-located.

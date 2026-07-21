# Task 03: `ProgramRequirementsUpsertRequest` Pydantic Schema

## Objective
Define a Pydantic request model for `POST /internal/program-requirements` covering every column on
the now-extended `program_requirements` table (Task 02), matching the style of
`app/schemas/visa.py::VisaRequirementsRequest`.

## Background
The RAG service has no ORM (`services/rag/app/core/database.py` uses raw `asyncpg`); the only place a
`program_requirements`-shaped Pydantic model exists today is `app/schemas/scoring.py::ProgramRequirements`
(lines 19-26), which deliberately omits `university`/`country`/`source_url`/`content_hash` because
it's a *read*-side model used only by the scoring/gates code path
(`app/services/scoring.py::get_program_requirements`, `app/services/gates.py::check_hard_gates`). That
model must not be reused or widened for the upsert endpoint — conflating a narrow read model with a
full write model would either break the existing gates code (extra required fields) or silently allow
unvalidated data into the write path. A new, separate model is needed for the write side, mirroring
how `VisaRequirementsRequest` is entirely separate from any read-side visa model.

## Scope
Only a new Pydantic schema file. No service or endpoint code in this task (Task 05).

## Implementation Steps
- [ ] Create `services/rag/app/schemas/program_requirements.py` with a
      `ProgramRequirementsUpsertRequest(BaseModel)` containing:
      - `university: str` (required — part of the upsert key)
      - `country: str` (required — part of the upsert key)
      - `degree_level: str` (required — part of the upsert key)
      - `min_ects: Optional[int] = None`
      - `min_gpa: Optional[float] = None`
      - `min_ielts: Optional[float] = None`
      - `required_citizenship: Optional[str] = None` (matches the existing column name post-migration
        `008`'s rename — **not** `citizenship_required`, which the ticket's summary text uses loosely
        but the actual column is `required_citizenship`)
      - `min_work_experience: Optional[int] = None`
      - `source_url: Optional[str] = None`
      - `content_hash: Optional[str] = None`
- [ ] Match `VisaRequirementsRequest`'s style: flat `Field(...)` declarations with `description=`
      strings, `Optional[...] = None` for nullable columns, no nested nullable nesting beyond what's
      needed.
- [ ] Do not add any field not present on the `program_requirements` table after Task 02 — this schema
      should be a direct mirror of the table, not an expanded API surface.

## Expected Files/Modules
- `services/rag/app/schemas/program_requirements.py` (new)

## Dependencies
- Task 02 (the table must have `content_hash`/`source_url` columns for this schema to make sense as a
  write model, though the schema file itself has no runtime dependency on the migration having run).

## Risks
- **Column name mismatch.** The actual DB column is `required_citizenship` (renamed by migration `008`
  from `citizenship_required`). GOA-088's own summary text says "citizenship_required" when describing
  what `MastersPortalAdapter` should populate — using that literal name in the schema would silently
  create a field that never maps to the real column. Use `required_citizenship` to match the table and
  the existing `ProgramRequirements` read-model naming (`app/schemas/scoring.py:23`).
- **Conflating with the existing read-side `ProgramRequirements` model.** Keep this as a fully separate
  class in a separate file — do not attempt to extend or reuse `app/schemas/scoring.py::ProgramRequirements`
  for the write path.

## Definition of Done
- `ProgramRequirementsUpsertRequest` round-trips a full valid payload via `.model_dump()`.
- Omitting `university`, `country`, or `degree_level` raises a `ValidationError`.
- All other fields are optional and default to `None`.
- Field name for citizenship is `required_citizenship`, consistent with the actual DB column.

## Acceptance Criteria
- A unit test (mirroring `tests/test_visa.py:36-66`'s schema-validation section) confirms: valid
  payload passes; missing required field raises; `model_dump()` produces a plain dict ready for
  `**data` expansion into the Task 05 service function.

## Notes for Implementation
- This schema is consumed directly by Task 05's endpoint (`request.model_dump()` passed to the
  service function), following the exact `api/visa.py:12-16` pattern — no additional
  serialization/deserialization layer should be introduced.
- Do not add a `deadline`-style date-coercion validator here — `program_requirements` has no deadline
  field; that concern is specific to Task 04's `scholarship_programs` schema.

# Task 04: `ScholarshipProgramUpsertRequest` Pydantic Schema

## Objective
Define a Pydantic request model for `POST /internal/scholarship-programs` matching the
`scholarship_programs` table created in Task 01, following `app/schemas/visa.py`'s style.

## Background
`scholarship_programs` is a brand-new table with no prior Pydantic model anywhere in the codebase.
Its DDL (Task 01) includes a `deadline DATE` column and an `eligibility JSONB NOT NULL DEFAULT '{}'`
column — both need explicit handling: `deadline` will arrive from adapters as free-text-derived
strings that may not always parse cleanly (see Task 10/11), and `eligibility` needs to serialize to
JSONB the same way `visa_service.py` already handles `requirements`/`proof_of_funds`
(`json.dumps(...)` before the `::jsonb` cast, per `visa_service.py:21-23`).

## Scope
Only a new Pydantic schema file. No service or endpoint code in this task (Task 06).

## Implementation Steps
- [ ] Create `services/rag/app/schemas/scholarship_programs.py` with a
      `ScholarshipProgramUpsertRequest(BaseModel)` containing:
      - `name: str` (required — part of the upsert key)
      - `provider: str` (required — part of the upsert key)
      - `source_url: str` (required, matches the table's `NOT NULL`)
      - `country: Optional[str] = None`
      - `degree_level: Optional[str] = None`
      - `award_amount: Optional[str] = None` (free-text, matches the table's `VARCHAR(255)` — do not
        make this numeric; award structures vary too much, per the ticket's own DDL comment)
      - `deadline: Optional[date] = None`
      - `eligibility: dict = Field(default_factory=dict)`
      - `citizenship_eligible: bool = True`
      - `min_gpa: Optional[float] = None`
      - `min_ielts: Optional[float] = None`
      - `content_hash: Optional[str] = None`
- [ ] Add a `field_validator`/`validator` on `deadline` that accepts either a proper ISO date string, a
      `date` object, or `None` — and coerces any value it cannot confidently parse to `None` rather
      than raising, so a scholarship with an unparseable deadline string is still stored (see Task 10/
      11's extraction notes on inconsistent deadline formats). This is a validation *behavior* decision
      worth flagging explicitly in code comments/PR description, since silently dropping to `None`
      trades strictness for availability — confirm this tradeoff is acceptable (see master plan's Open
      Questions) rather than assuming it silently.
- [ ] Match `VisaRequirementsRequest`'s style otherwise: flat fields, `Field(..., description=...)`.

## Expected Files/Modules
- `services/rag/app/schemas/scholarship_programs.py` (new)

## Dependencies
- Task 01 (the table this schema mirrors must exist for the mapping to be meaningful, though the
  schema file itself has no runtime dependency on the migration having run).

## Risks
- **`deadline` parsing ambiguity.** Source pages will state dates in varied formats ("15 October
  2026", "rolling", "TBC for 2027 cycle"). Silently coercing unparseable values to `None` is a
  deliberate choice this task makes explicit — the alternative (rejecting the whole record) would mean
  a scholarship with everything else valid gets dropped entirely just because its deadline text was
  unusual. This tradeoff should be called out in the PR rather than buried in a validator.
- **`eligibility` shape is unconstrained (`dict`).** The ticket's DDL only specifies "structured
  eligibility rules" without a fixed shape — treat it as an open JSONB bag (matching how
  `requirements`/`proof_of_funds` are treated for `visa_requirements`), not a strictly-typed nested
  model, to avoid inventing a schema the ticket doesn't specify.

## Definition of Done
- `ScholarshipProgramUpsertRequest` round-trips a full valid payload via `.model_dump()`.
- Omitting `name`, `provider`, or `source_url` raises a `ValidationError`.
- A `deadline` given as a valid ISO date string parses to a `date`; an unparseable string (or absent
  value) results in `None`, not an exception.
- `eligibility` defaults to `{}` when omitted; `citizenship_eligible` defaults to `True` when omitted,
  matching the table's `DEFAULT TRUE`.

## Acceptance Criteria
- A unit test (mirroring `tests/test_visa.py:36-66`) confirms: valid payload passes; missing required
  field raises; malformed `deadline` does not raise and results in `None`; `model_dump()` produces a
  plain dict with `eligibility` as a plain `dict` (not a nested Pydantic object) ready for
  `json.dumps()` in Task 06's service function.

## Notes for Implementation
- This schema is consumed directly by Task 06's endpoint, following the `api/visa.py:12-16` pattern.
- `award_amount` staying free-text (not numeric) is a deliberate carry-over from the ticket's own DDL
  comment ("varies: monthly stipend, full tuition") — do not "improve" this into a structured
  amount/currency pair without confirming with the ticket owner first, since it would change the wire
  contract Task 10/11's adapters must produce.

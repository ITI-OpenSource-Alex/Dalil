# Task 02: Extend `VisaRequirementsRequest` Pydantic Schema

## Goal
Add `egyptian_specific: bool` and a properly typed, nested `proof_of_funds` model to
`VisaRequirementsRequest` in `services/rag/app/schemas/visa.py`.

## Why this task exists
The current schema is missing `egyptian_specific` entirely and defines `proof_of_funds` as a bare,
untyped `Optional[dict]`. GOA-086 specifies an exact JSON shape for `proof_of_funds` (amount_eur,
accepted_account_types, blocked_account_providers, minimum_balance_period_days,
sponsor_letter_accepted, notes_egypt) that should be validated at the API boundary, not passed
through blindly. This schema is what every adapter (Tasks 07–15) and the real upsert logic
(Task 03) will produce/consume.

## Prerequisites
- None hard — Pydantic model definitions don't require the DB column from Task 01 to exist to
  compile or validate. Sequencing after Task 01 is recommended only for narrative consistency
  (schema should reflect the final agreed column set), not a technical blocker.

## Scope
Only `services/rag/app/schemas/visa.py`.

## Implementation Steps
- [ ] Add a new `ProofOfFunds(BaseModel)` with fields matching the ticket exactly:
      `amount_eur: Optional[float]`, `accepted_account_types: Optional[List[str]]`,
      `blocked_account_providers: Optional[List[str]]`,
      `minimum_balance_period_days: Optional[int]`, `sponsor_letter_accepted: Optional[bool]`,
      `notes_egypt: Optional[str]`.
- [ ] Change `VisaRequirementsRequest.proof_of_funds` from `Optional[dict]` to
      `Optional[ProofOfFunds]`.
- [ ] Add `egyptian_specific: bool = Field(..., description="True if this record is Egypt-applicant
      specific")` to `VisaRequirementsRequest` as a required field (every record the 9 new adapters
      produce sets this explicitly — see Task 01's plan-level assumption).
- [ ] Confirm `request.model_dump()` (used in `app/api/visa.py::handle_visa_requirements`) still
      produces a plain, JSON-serializable nested dict (Pydantic v2's `model_dump()` recurses into
      nested models automatically — verify this, don't assume).

## Files Expected to Change
- `services/rag/app/schemas/visa.py`

## Acceptance Criteria
- A request missing `egyptian_specific` is rejected with a `422`/`ValidationError`.
- A request with a malformed `proof_of_funds` (e.g. `amount_eur` as a string) is rejected.
- A fully valid payload (including nested `proof_of_funds`) passes validation and
  `model_dump()` returns a plain nested dict with all fields present.

## Testing
- New unit tests in `services/rag/tests/test_visa.py` (first entries in this new test file):
  - Valid full payload → passes validation.
  - Missing `egyptian_specific` → raises `ValidationError`.
  - `proof_of_funds.amount_eur` as a non-numeric string → raises `ValidationError`.
  - `model_dump()` output shape matches the expected nested dict (spot-check keys and types).

## Notes
- Task 03 (real upsert implementation) consumes this schema's output directly — keep field names
  identical to what the DB upsert expects to write into the `requirements`/`proof_of_funds` JSONB
  columns.
- This task does not touch `app/api/visa.py` or `app/services/visa_service.py` — those are Tasks 03
  and 04.

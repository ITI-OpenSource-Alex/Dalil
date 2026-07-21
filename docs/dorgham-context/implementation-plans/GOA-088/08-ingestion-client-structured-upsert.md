# Task 08: Ingestion `client.py` — Structured Upsert Functions

## Objective
Add `upsert_program_requirement(record: dict) -> bool` and
`upsert_scholarship_program(record: dict) -> bool` to `services/ingestion/client.py`, calling the two
new RAG internal endpoints (Tasks 05/06), cloned from the existing `upsert_visa_requirement`.

## Background
`services/ingestion/client.py:41-63` already implements the exact call shape needed:

```
def upsert_visa_requirement(record: dict) -> bool:
    url = f"{settings.rag_service_url}/internal/visa-requirements"
    headers = get_headers()
    response = requests.post(url, json=record, headers=headers, timeout=15)
    ...
```

`get_headers()` (`client.py:7-12`) already sets `X-Internal-Api-Key` from `settings.internal_api_key`
— no new ingestion-side config is needed. This task adds two more functions following this identical
shape, one per new endpoint.

## Scope
Only `services/ingestion/client.py` (append two functions). No changes to `config.py`,
`get_headers()`, or the existing `upsert_visa_requirement`/`upsert_chunks`/`check_existing_chunks`
functions.

## Implementation Steps
- [ ] Add `upsert_program_requirement(record: dict) -> bool`, POSTing to
      `f"{settings.rag_service_url}/internal/program-requirements"`, using `get_headers()`,
      `timeout=15`, identical success/error handling to `upsert_visa_requirement` (log + return `True`
      on `200`; log + `response.raise_for_status()` on non-`200`; log + re-raise on connection
      failure).
- [ ] Add `upsert_scholarship_program(record: dict) -> bool`, POSTing to
      `f"{settings.rag_service_url}/internal/scholarship-programs"`, same pattern.
- [ ] Do **not** add retry/backoff decorators to these new functions — match the existing
      `upsert_visa_requirement`'s behavior exactly for consistency. (This repository-wide gap —
      no retry on any `client.py` upsert call — is documented as pre-existing technical debt in the
      master plan's Future Improvements, not something this task should fix unilaterally; fixing it
      here would make these two new functions behave inconsistently with `upsert_visa_requirement`
      and `upsert_chunks`, which is worse than leaving all of them consistently un-retried.)

## Expected Files/Modules
- `services/ingestion/client.py` (edited — two functions appended)

## Dependencies
- Task 05 (`POST /internal/program-requirements` must exist for this function's target URL to be
  meaningful — though the function itself can be written and unit-tested with a mocked `requests.post`
  before Task 05 lands).
- Task 06 (`POST /internal/scholarship-programs`, same relationship).

## Risks
- **Inherited no-retry gap.** These two new functions will fail outright (raise) on any transient
  network blip or RAG-service restart mid-run, exactly like `upsert_visa_requirement` does today. This
  is a known, accepted limitation carried forward from the existing pattern — not a regression
  introduced by this task, and not something to silently "fix" here (see Background/Implementation
  Steps above).
- **Synchronous call inside the async orchestrator loop.** Like `upsert_visa_requirement`, these use
  blocking `requests.post` rather than an async HTTP client, so each call blocks the event loop for its
  duration. This is consistent with existing behavior and not a regression; Task 12 (orchestrator
  wiring) inherits this, roughly proportional to however many more structured records exist versus
  visa records per run.

## Definition of Done
- Both functions exist with signatures matching `upsert_visa_requirement`'s shape.
- Both successfully POST to their respective endpoints and return `True` on `200`.
- Both raise on non-`200` responses and on connection failures, matching existing error-handling
  convention.

## Acceptance Criteria
- Unit tests (mirroring whatever pattern `tests/test_client.py` uses for `upsert_visa_requirement`)
  confirm: correct URL constructed from `settings.rag_service_url`; correct headers sent; `True`
  returned on `200`; exception raised and logged on non-`200` and on connection error.

## Notes for Implementation
- These functions are the two call sites Task 12's orchestrator wiring will invoke — their signatures
  (`record: dict) -> bool`) must match what Task 12 expects to call inside its per-record try/except
  loop.
- Do not introduce a shared "upsert client" abstraction wrapping all four upsert functions
  (`upsert_visa_requirement`, `upsert_chunks`, and these two new ones) — the existing codebase keeps
  each as an independent flat function in `client.py`, and this ticket should not introduce new
  abstraction beyond what it needs.

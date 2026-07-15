# Task 06: Ingestion Client — `upsert_visa_requirement` Function

## Goal
Add a `upsert_visa_requirement(record: dict) -> bool` function to `services/ingestion/client.py`
that POSTs a single structured visa record to `/internal/visa-requirements`.

## Why this task exists
`client.py` currently only has `check_existing_chunks` and `upsert_chunks` for the `documents`
pipeline — there is no client-side function to call the visa endpoint at all. Task 16 (wiring the 9
adapters into the ingestion pipeline) needs this function to exist to perform the structured-data
half of the dual write.

## Prerequisites
- None hard for writing the function itself — it mirrors `upsert_chunks`'s existing structure and
  reuses `get_headers()`, which already sends `X-Internal-Api-Key`.
- Recommended (not required) to sequence after Task 04 (auth), so this function can be
  integration-tested against a real, protected endpoint rather than only unit-tested with mocks.

## Scope
Only `services/ingestion/client.py`.

## Implementation Steps
- [ ] Add `def upsert_visa_requirement(record: dict) -> bool:` following the exact structure of the
      existing `upsert_chunks` function.
- [ ] Build the URL as `f"{settings.rag_service_url}/internal/visa-requirements"`.
- [ ] Call `get_headers()` for the request headers (already includes `X-Internal-Api-Key`).
- [ ] POST with `requests.post(url, json=record, headers=headers, timeout=15)` — note this sends a
      single object, not a list, matching the existing `VisaRequirementsRequest` schema shape (no
      batch wrapper).
- [ ] On `response.status_code == 200`: log success, return `True`.
- [ ] On any other status: log the error body and call `response.raise_for_status()` (matching
      `upsert_chunks`'s error-handling pattern).
- [ ] Wrap the whole call in `try/except`, logging and re-raising, matching `upsert_chunks`.

## Files Expected to Change
- `services/ingestion/client.py`

## Acceptance Criteria
- Function sends a well-formed `POST` with the correct URL, JSON body, and
  `X-Internal-Api-Key` header.
- Returns `True` on a `200` response.
- Raises (after logging) on any non-`200` response.
- Unit-testable in isolation by mocking `requests.post` — does not require a live RAG service.

## Testing
- Unit test mocking `requests.post`:
  - Assert the constructed URL matches `{rag_service_url}/internal/visa-requirements`.
  - Assert headers include `X-Internal-Api-Key` with the configured value.
  - Assert the JSON body passed through matches the input `record` unmodified.
  - Assert return value is `True` on a mocked `200` response.
  - Assert an exception propagates (after logging) when the mocked response is `401` or `500`.

## Notes
- Task 16 will call this function once per structured visa record accumulated during an ingestion
  run (a run may accumulate zero, one, or many records — see Tasks 07–15 on adapters potentially
  returning multiple records per page).
- The function intentionally takes a single `dict`, not a list, to match the existing
  single-object `/internal/visa-requirements` endpoint contract (Task 02/03) — no batching endpoint
  exists or is planned for this ticket.

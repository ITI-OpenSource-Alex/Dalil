# Task 04: Extract Shared Internal-API-Key Auth and Secure the Visa Endpoint

## Goal
Move the internal-API-key check out of `app/api/documents.py` into a shared module, and apply it to
`POST /internal/visa-requirements`, which currently has no authentication at all.

## Why this task exists
Confirmed by reading `app/main.py` (no global auth middleware exists) and `app/api/visa.py` (no
`Security(...)` dependency present) that `/internal/visa-requirements` is genuinely unauthenticated
today — any caller can write arbitrary visa data. `app/api/documents.py` already implements the
exact check needed (`verify_api_key` / `api_key_header` / `API_KEY_NAME`), it's just not shared.

## Prerequisites
- None hard — this only touches routing/auth, not persistence logic, so it can be implemented in
  parallel with Tasks 01–03.
- Recommended to land before Task 18 (integration testing), since integration tests will exercise
  the now-protected endpoint.

## Scope
- New `services/rag/app/core/security.py`.
- Edits to `services/rag/app/api/documents.py` (import only, no behavior change).
- Edit to `services/rag/app/api/visa.py` (add the auth dependency).

## Implementation Steps
- [ ] Create `services/rag/app/core/security.py` containing `API_KEY_NAME`, `api_key_header =
      APIKeyHeader(...)`, and `async def verify_api_key(...)`, moved verbatim from
      `app/api/documents.py` (same logic: compare header value against `settings.internal_api_key`,
      raise `401` on mismatch/missing).
- [ ] Update `app/api/documents.py` to import `verify_api_key` from `app.core.security` instead of
      defining it locally; delete the now-duplicated local definitions.
- [ ] Update `app/api/visa.py`'s `handle_visa_requirements` route signature to add
      `_ = Security(verify_api_key)` (imported from `app.core.security`), matching the pattern in
      `documents.py`'s routes.
- [ ] Grep the codebase for any other import of `verify_api_key`/`api_key_header` from
      `app.api.documents` to make sure nothing else breaks when the local definitions are removed.

## Files Expected to Change
- `services/rag/app/core/security.py` (new)
- `services/rag/app/api/documents.py`
- `services/rag/app/api/visa.py`

## Acceptance Criteria
- `POST /internal/documents` behavior is unchanged: still requires `X-Internal-Api-Key`, still
  returns `401` on missing/invalid key.
- `POST /internal/visa-requirements` now returns `401` without a valid `X-Internal-Api-Key` header,
  and proceeds to the (real, per Task 03) upsert logic when the header is correct.

## Testing
- Confirm any existing tests exercising `/internal/documents` still pass unmodified.
- New tests (in `test_visa.py` or a dedicated `test_visa_auth.py`) using FastAPI's `TestClient`:
  - No `X-Internal-Api-Key` header → `401`.
  - Wrong header value → `401`.
  - Correct header value (matching `settings.internal_api_key`) → request proceeds to the handler
    (asserted via a `200`/expected success response, not just "not 401").

## Notes
- The ingestion-side client (Task 06) must send this same header when calling the endpoint — it
  already does, via `client.py::get_headers()`, so no ingestion-side change is required for this
  task specifically.
- This task can be done at any point relative to Tasks 01–03 without conflict, since it touches
  routing, not the upsert logic itself.

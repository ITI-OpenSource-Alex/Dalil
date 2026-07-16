# Task 09: `CampusFranceEgyptAdapter`

## Goal
Implement `CampusFranceEgyptAdapter`, scraping French student-visa procedural requirements as
published by Campus France Egypt, producing both RAG document chunks and structured
`visa_requirements` record(s).

## Why this task exists
GOA-086 explicitly names this adapter. It's one of the 7 adapters the ticket requires unit tests
for, and covers the "Études en France" procedure that Egyptian applicants to France must go through
before a national visa application.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL for the Campus France Egypt procedure page needs confirmation (see
  main plan, Question #2). Fixture-based development can proceed regardless.

## Scope
One new adapter file: `services/ingestion/app/adapters/campus_france_egypt.py`, plus its unit
test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site).
- [ ] Constructor: `source_name="campus_france_egypt"`, `category="visa"`, `country="France"`,
      `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key: `issuing_body="Campus France Egypt"`,
      `visa_type` e.g. `"Student Visa (Long Stay — VLS-TS)"`, `egyptian_specific=True`,
      `requirements` JSON reflecting the Études en France procedural steps as actually stated on the
      source page, `proof_of_funds` if the page states a required amount, `content_hash` computed
      from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if crawling is required; otherwise single-page default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/campus_france_egypt.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="France"`.
- At least one dict includes populated `visa_requirements`.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path, partial-data
  robustness (procedural steps missing some fields), Arabic-skip.

## Notes
- Must be added to both ingestion entry points in Task 16.
- No known overlap with other adapters' `(country, visa_type, issuing_body)` keys since France is
  unique to this adapter among the 9.

# Task 14: `SpainVisaEgyptAdapter`

## Goal
Implement `SpainVisaEgyptAdapter`, scraping Spanish student-visa requirements as they apply to
Egypt-based applicants, producing both RAG document chunks and structured `visa_requirements`
record(s).

## Why this task exists
GOA-086 explicitly names this adapter. It's one of the 7 adapters the ticket requires unit tests
for.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL/portal (Spanish Consulate Cairo directly, or an outsourced partner
  such as BLS International) needs confirmation (see main plan, Question #2). Fixture-based
  development can proceed regardless.

## Scope
One new adapter file: `services/ingestion/app/adapters/spain_visa_egypt.py`, plus its unit test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site, unless the confirmed source turns out to be JS-heavy —
      verify before assuming).
- [ ] Constructor: `source_name="spain_visa_egypt"`, `category="visa"`, `country="Spain"`,
      `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key: `issuing_body` set to whatever the confirmed
      actual processing body is (Consulate General of Spain in Cairo, or an outsourced partner),
      `visa_type` e.g. `"Student Visa (National Visa — Type D)"`, `egyptian_specific=True`,
      `requirements`/`proof_of_funds`/`processing_days_min/max` populated from what the source page
      actually states, `content_hash` computed from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if crawling is required; otherwise single-page default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/spain_visa_egypt.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="Spain"`.
- At least one dict includes populated `visa_requirements`.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path, partial-data
  robustness, Arabic-skip.

## Notes
- Must be added to both ingestion entry points in Task 16.
- Same VFS Global Egypt coordination note as Task 13 applies here if Spain's visa processing is
  outsourced through VFS.

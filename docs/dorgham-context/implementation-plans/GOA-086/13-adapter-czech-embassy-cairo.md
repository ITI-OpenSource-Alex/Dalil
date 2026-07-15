# Task 13: `CzechEmbassyCairoAdapter`

## Goal
Implement `CzechEmbassyCairoAdapter`, scraping Czech student-visa requirements as published by the
Czech Embassy in Cairo, producing both RAG document chunks and structured `visa_requirements`
record(s).

## Why this task exists
GOA-086 explicitly names this adapter. It's one of the 7 adapters the ticket requires unit tests
for.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL for the Czech Embassy Cairo visa-requirements page needs
  confirmation (see main plan, Question #2). Fixture-based development can proceed regardless.

## Scope
One new adapter file: `services/ingestion/app/adapters/czech_embassy_cairo.py`, plus its unit
test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site).
- [ ] Constructor: `source_name="czech_embassy_cairo"`, `category="visa"`,
      `country="Czech Republic"`, `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key: `issuing_body="Embassy of the Czech Republic
      in Cairo"`, `visa_type` e.g. `"Student Visa (Long-term / Type D)"`, `egyptian_specific=True`,
      `requirements`/`proof_of_funds`/`processing_days_min/max` populated from what the source page
      actually states, `content_hash` computed from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if crawling is required; otherwise single-page default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/czech_embassy_cairo.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="Czech Republic"`.
- At least one dict includes populated `visa_requirements`.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path, partial-data
  robustness, Arabic-skip.

## Notes
- Must be added to both ingestion entry points in Task 16.
- If VFS Global Egypt (Task 11) also processes Czech visa applications, coordinate `issuing_body`
  naming so this adapter's records (keyed to the embassy) and VFS's records (if any, keyed to VFS)
  don't collide on the same `(country, visa_type, issuing_body)` unique key — they shouldn't, since
  `issuing_body` differs, but confirm the `visa_type` framing is consistent/non-duplicative between
  the two.

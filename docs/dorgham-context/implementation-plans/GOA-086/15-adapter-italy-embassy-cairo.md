# Task 15: `ItalyEmbassyCairoAdapter`

## Goal
Implement `ItalyEmbassyCairoAdapter`, scraping Italian student-visa requirements as published by the
Italian Embassy/Consulate in Cairo (or its outsourced visa partner), producing both RAG document
chunks and structured `visa_requirements` record(s).

## Why this task exists
GOA-086 explicitly names this adapter. It's the last of the 7 adapters the ticket requires unit
tests for.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL/portal (Italian Embassy/Consulate Cairo directly, or an outsourced
  partner) needs confirmation (see main plan, Question #2). Fixture-based development can proceed
  regardless.

## Scope
One new adapter file: `services/ingestion/app/adapters/italy_embassy_cairo.py`, plus its unit
test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site, unless the confirmed source turns out to be JS-heavy —
      verify before assuming).
- [ ] Constructor: `source_name="italy_embassy_cairo"`, `category="visa"`, `country="Italy"`,
      `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key: `issuing_body` set to whatever the confirmed
      actual processing body is, `visa_type` e.g. `"Student Visa (National Visa — Type D)"`,
      `egyptian_specific=True`, `requirements`/`proof_of_funds`/`processing_days_min/max` populated
      from what the source page actually states, `content_hash` computed from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if crawling is required; otherwise single-page default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/italy_embassy_cairo.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="Italy"`.
- At least one dict includes populated `visa_requirements`.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path, partial-data
  robustness, Arabic-skip.

## Notes
- Must be added to both ingestion entry points in Task 16.
- Same VFS Global Egypt coordination note as Tasks 13/14 applies here if Italy's visa processing is
  outsourced through VFS.
- This is the last of the 9 individual adapter tasks — once Tasks 07–15 are all complete, proceed to
  Task 16 (wiring).

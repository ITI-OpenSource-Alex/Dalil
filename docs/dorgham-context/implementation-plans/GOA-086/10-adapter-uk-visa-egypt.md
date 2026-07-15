# Task 10: `UKVISAEgyptAdapter`

## Goal
Implement `UKVISAEgyptAdapter`, scraping UK student-visa requirements as they apply to applicants
processed via the UK's Egypt visa-application channel, producing both RAG document chunks and
structured `visa_requirements` record(s).

## Why this task exists
GOA-086 explicitly names this adapter as one of the 9 required. Note: unlike 7 of the other
adapters, this one is **not** listed under the ticket's "Unit" test section — only implied via the
"Run all 9 adapters" integration criterion. The main plan (Question #5) recommends building a unit
test anyway, since the cost is low and consistency across adapters simplifies review.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL/portal for UK visa information relevant to Egypt-based applicants
  needs confirmation (see main plan, Question #2). Fixture-based development can proceed regardless.
- **Open item to confirm with ticket owner**: whether the omission of this adapter from the ticket's
  "Unit" list is intentional (see main plan, Question #5) — proceed with a unit test by default
  unless told otherwise.

## Scope
One new adapter file: `services/ingestion/app/adapters/uk_visa_egypt.py`, plus its unit test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site, unless the actual UKVI portal turns out to be JS-heavy —
      confirm during URL research before assuming `BaseAdapter` is correct).
- [ ] Constructor: `source_name="uk_visa_egypt"`, `category="visa"`, `country="UK"`,
      `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key: `issuing_body` set to whatever the actual
      processing body is (UKVI directly, or an outsourced partner like TLScontact/VFS depending on
      the confirmed source), `visa_type` e.g. `"Student Visa (Student Route)"`,
      `egyptian_specific=True`, `requirements`/`proof_of_funds`/`processing_days_min/max` populated
      from what the source page actually states, `content_hash` computed from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if crawling is required; otherwise single-page default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/uk_visa_egypt.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`, `country="UK"`.
- At least one dict includes populated `visa_requirements`.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (recommended per main plan, even though not strictly required by the ticket's own "Unit"
  list): happy path, partial-data robustness, Arabic-skip.

## Notes
- Must be added to both ingestion entry points in Task 16.
- If the confirmed UK visa-info source for Egypt turns out to route through VFS Global (the same
  outsourced centre as Task 11), coordinate `issuing_body` naming with Task 11 so the two adapters'
  records remain distinguishable by `(country, visa_type, issuing_body)`.

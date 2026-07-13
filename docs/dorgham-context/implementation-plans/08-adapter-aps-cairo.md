# Task 08: `APSCairoAdapter`

## Goal
Implement `APSCairoAdapter`, scraping APS (Akademische Prüfstelle) certification requirements from
APS Cairo, producing both RAG document chunks and structured `visa_requirements` record(s).

## Why this task exists
GOA-086 explicitly names this adapter and calls out "APS certificate" in its Egypt-specific context.
It's one of the 7 adapters the ticket requires unit tests for, and is the direct source for the
ticket's Definition-of-Done integration check "verify APS certificate query."

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`).
- **Open item**: exact target URL for APS Cairo's requirements page needs confirmation (see main
  plan, Question #2). Fixture-based development can proceed regardless.
- **Judgment call to resolve during implementation**: APS Cairo issues a *certificate*, not a visa
  itself — it's a prerequisite step for German student visa applications. Recommend recording this
  as `country="Germany"`, `issuing_body="APS Cairo"`, `visa_type` something like
  `"Student Visa (APS Certificate Requirement)"`, with the `requirements` JSON describing the APS
  certification process itself. Confirm this framing doesn't conflict with how
  `GermanEmbassyCairoAdapter` (Task 07) or `FintibaSperrkontoAdapter` (Task 12) key their own
  `visa_type` values for the same destination country, to keep `(country, visa_type, issuing_body)`
  meaningfully distinct across the three.

## Scope
One new adapter file: `services/ingestion/app/adapters/aps_cairo.py`, plus its unit test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static site).
- [ ] Constructor: `source_name="aps_cairo"`, `category="visa"`, `country="Germany"`,
      `min_delay=2.0, max_delay=3.0`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s).
- [ ] Populate the optional `"visa_requirements"` key with the APS certification process captured as
      structured fields per the judgment call above — `issuing_body="APS Cairo"`,
      `egyptian_specific=True`, `requirements` JSON describing document checklist / eligibility
      (e.g. Thanaweya Amma recognition requirements feed into this, since APS evaluates Egyptian
      secondary/university certificates), `processing_days_min/max` if stated, `content_hash`
      computed from structured fields.
- [ ] Implement Arabic-page skip.
- [ ] Implement `extract_urls` if the site requires crawling; otherwise rely on the single-page
      default.
- [ ] Use inherited `fetch_page` for automatic backoff.

## Files Expected to Change
- `services/ingestion/app/adapters/aps_cairo.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`.
- At least one dict includes populated `visa_requirements` describing the APS process.
- Content is specific enough that a later `/query` call (Task 18) about "APS certificate" can be
  meaningfully answered from the resulting document chunks.
- Arabic-only fixture returns `[]` without raising.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path, partial-data
  robustness, Arabic-skip, and — since APS involves a multi-step process — a test that a fixture
  describing multiple APS pathways (e.g. university-track vs. non-university-track) yields the
  correct number of `visa_requirements` entries.

## Notes
- This adapter's output directly feeds Task 18's "verify an APS certificate query" integration
  check — make sure the fixture/real content is substantive enough (not a one-line stub) for that
  check to be meaningful.
- Must be added to both ingestion entry points in Task 16.

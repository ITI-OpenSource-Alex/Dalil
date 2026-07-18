# Task 07: `GermanEmbassyCairoAdapter`

## Goal
Implement `GermanEmbassyCairoAdapter`, scraping German student-visa requirements as published by the
German Embassy in Cairo, producing both RAG document chunks and structured `visa_requirements`
record(s).

## Why this task exists
GOA-086 explicitly names this adapter. This is one of the 7 static-site adapters the ticket requires
unit tests for. It's a primary source for the ticket's Egypt-specific context items (APS reference,
general national visa requirements, proof-of-funds pointers that cross-reference the
Fintiba/Sperrkonto adapter).

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BaseAdapter`) — this adapter's constructor
  passes `min_delay=2.0, max_delay=3.0`.
- **Open item**: the exact target URL(s) for the German Embassy Cairo visa-requirements page(s) are
  not specified in the ticket and must be confirmed (see main plan, Question #2) before scraping
  real markup. Fixture-based development and unit testing can proceed regardless, using a
  representative fixture HTML.

## Scope
One new adapter file: `services/ingestion/app/adapters/german_embassy_cairo.py`, plus its unit
test(s).

## Implementation Steps
- [ ] Subclass `BaseAdapter` (static httpx + BeautifulSoup — this site is not JS-heavy).
- [ ] Constructor: `source_name="german_embassy_cairo"`, `category="visa"`, `country="Germany"`,
      `min_delay=2.0, max_delay=3.0`, `base_url`/`target_url` set once confirmed (see Prerequisites).
- [ ] Implement `extract_documents(html, url)` returning the standard chunk-shaped dict(s)
      (`source`, `category`, `country`, `url`, `content`), matching the existing adapter pattern
      (e.g. `daad.py`).
- [ ] On the same dict(s), additionally populate an optional `"visa_requirements"` key: a
      `list[dict]` (0, 1, or more entries) shaped per the ticket's `visa_requirements` columns —
      `visa_type`, `issuing_body="German Embassy Cairo"`, `requirements` (JSON capturing what the
      page actually states — do not fabricate fields the source doesn't mention), `proof_of_funds`
      (populate only what's stated; leave the rest `None`), `processing_days_min/max` if stated,
      `notes`, `source_url`, `egyptian_specific=True`, and a deterministically computed
      `content_hash` (e.g. sha256 of the structured fields, not raw HTML).
- [ ] Implement Arabic-page skip: if the page is Arabic-only (`<html lang="ar">` or predominantly
      non-Latin-script text), return `[]` from `extract_documents` rather than raising.
- [ ] If the site requires crawling from an index to detail pages, implement `extract_urls(html)`
      following the `DAADAdapter` pattern; otherwise rely on the base class's single-page default.
- [ ] Use inherited `fetch_page`/`fetch_binary` (do not make raw `httpx` calls) so
      `with_httpx_backoff` (429/503 retry) applies automatically.

## Files Expected to Change
- `services/ingestion/app/adapters/german_embassy_cairo.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended — unit tests for this adapter)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="Germany"`.
- At least one returned dict includes a populated `"visa_requirements"` list when the fixture page
  contains identifiable visa requirement content.
- Arabic-only fixture input returns `[]` without raising.
- Adapter respects `robots.txt` (inherited, no adapter-specific code needed) and uses the 2–3s delay
  range (inherited from Task 05's constructor args).

## Testing
- Unit test (ticket explicitly requires this adapter's unit test) using mocked fixture HTML,
  following the `mocker.patch("app.core.robots.robot_checker.is_allowed", ...)` +
  `mocker.patch.object(adapter, "fetch_page", ...)` pattern from `tests/test_adapters.py`:
  - Happy path: fixture HTML → correct document shape + populated `visa_requirements`.
  - Partial data: fixture missing `processing_days_min/max` → adapter doesn't crash, fields are
    `None`.
  - Arabic page → `[]`, `fetch_page` not called past the robots check as applicable.
  - Multi-record fixture (page describing 2+ visa sub-types) → `visa_requirements` list has 2+
    entries.

## Notes
- This adapter must be added to both `handler.py` and `run_orchestrator.py`'s adapter lists in
  Task 16 — not part of this task's scope.
- `category="visa"` is already an allowed value in the `documents.category` CHECK constraint — no
  migration needed.
- Coordinate with Task 08 (APS Cairo) and Task 12 (Fintiba): all three cover overlapping German
  student-visa context (APS certification, blocked account) — avoid duplicating the exact same
  `(country, visa_type, issuing_body)` key across adapters, since `issuing_body` should reflect the
  actual source (German Embassy Cairo vs. APS Cairo vs. Fintiba).

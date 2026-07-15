# Task 11: `VFSGlobalEgyptAdapter`

## Goal
Implement `VFSGlobalEgyptAdapter`, scraping VFS Global's Egypt-based visa application centre pages
(which handle outsourced visa application processing for multiple destination countries),
producing both RAG document chunks and structured `visa_requirements` record(s) — potentially
several per run, one per destination country VFS Global Egypt processes.

## Why this task exists
GOA-086 explicitly names this adapter and requires it to use Playwright (one of only two adapters
that do, per the ticket's implementation notes — this site is JS-heavy). It is **not** in the
ticket's "Unit" test list, only implied via "Run all 9 adapters." VFS Global Egypt is the clearest
real-world example in this ticket of a single source needing to emit **multiple** structured visa
records from one crawl, since it's a shared application centre for several countries' visas — this
is why the adapter contract (Task 05/06 groundwork) supports a `list[dict]` of visa records per
document, not a single optional record.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BasePlaywrightAdapter`).
- **Open item**: exact target URL(s) for VFS Global Egypt's country-specific visa pages need
  confirmation (see main plan, Question #2). Fixture-based development can proceed regardless.
- **Open item to confirm with ticket owner**: whether omission from the ticket's "Unit" list is
  intentional (main plan, Question #5) — proceed with a unit test by default.

## Scope
One new adapter file: `services/ingestion/app/adapters/vfs_global_egypt.py`, plus its unit test(s).
Uses `BasePlaywrightAdapter`, not `BaseAdapter`.

## Implementation Steps
- [ ] Subclass `BasePlaywrightAdapter` (JS-heavy site, per ticket's implementation notes).
- [ ] Constructor: `source_name="vfs_global_egypt"`, `category="visa"`, `country` — **do not
      hardcode a single country at the adapter level**; this adapter's per-page/per-country
      `country` value should be set per record inside `extract_documents`, since one crawl may cover
      several destination countries' visa processing pages.
      `min_delay=2.0, max_delay=3.0`, appropriate `wait_selector` for the site's rendered content.
- [ ] Implement `extract_urls(html)` to enumerate the country-specific sub-pages VFS Global Egypt
      exposes (e.g. Italy, Spain, Czech Republic sections), if the site structure requires crawling
      from an index page.
- [ ] Implement `extract_documents(html, url)`: for each country section identified on a page,
      produce one chunk-shaped document dict, and populate its `"visa_requirements"` key with one
      entry per distinct visa type/country combination found on that page — this is the adapter
      where returning **multiple** entries in the list is the norm, not the exception.
- [ ] Set `egyptian_specific=True` and `issuing_body="VFS Global Egypt"` on every record; set
      `country` per the specific destination country each record actually describes.
- [ ] Implement Arabic-page skip.
- [ ] Use inherited `fetch_page` (Playwright-based, already wrapped in `with_playwright_backoff`)
      rather than driving Playwright directly, to inherit retry/backoff for free.

## Files Expected to Change
- `services/ingestion/app/adapters/vfs_global_egypt.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`.
- At least one fixture scenario demonstrates a single document dict's `visa_requirements` list
  containing 2+ entries for different destination countries — this is the primary "multiple visa
  records from one adapter" coverage referenced in the main plan's edge cases.
- Arabic-only fixture content returns `[]` without raising.
- A simulated Playwright failure (timeout/navigation error) on this adapter does not crash the whole
  ingestion run when exercised via Task 16's isolation (verified there, not here, but the adapter
  itself must not swallow or mask exceptions in a way that breaks that isolation).

## Testing
- Unit test (recommended per main plan): mock Playwright's `fetch_page`
  (`mocker.patch.object(adapter, "fetch_page", ...)`, same pattern as existing adapter tests, which
  works because `extract_documents` can be tested independently of the actual browser automation)
  with fixture HTML covering multiple countries on one page; assert multiple `visa_requirements`
  entries with correct per-record `country` values; Arabic-skip test; partial-data robustness test.

## Notes
- This is one of only 2 Playwright-based adapters (with Task 12); expect this and Task 12 to be the
  most fragile/highest-maintenance adapters long-term (real site structure changes).
- Must be added to both ingestion entry points in Task 16, where the per-adapter failure isolation
  (`asyncio.gather(..., return_exceptions=True)`) matters most for this adapter specifically.
- Coordinate `issuing_body`/`country` naming with Task 10 (UK VI Egypt) and Tasks 13–15 (Czech,
  Spain, Italy) in case VFS Global Egypt's pages cover the same destination countries those adapters
  also target directly — avoid emitting duplicate/conflicting records for the same
  `(country, visa_type, issuing_body)` key from two different adapters (if VFS is the actual issuing
  body for a country, that country's dedicated embassy adapter should key its own records under the
  embassy's name, not VFS's, to keep the two distinct).

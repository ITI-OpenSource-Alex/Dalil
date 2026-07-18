# Task 10: `DAADAdapter.scrape_structured()`

## Objective
Add structured `scholarship_programs` extraction to `DAADAdapter`, exposed via a `scrape_structured()`
method, while keeping the existing chunk-document behavior unchanged.

## Background
`services/ingestion/app/adapters/daad.py` (52 lines) currently does no structured extraction —
`extract_documents()` grabs `main`/`#main-content`/`#content`/`.c-detail-page` text and returns only
the standard chunk dict. The adapter is a `BasePlaywrightAdapter` subclass that crawls up to 3 index
pages (`page=1..3`) of the DAAD scholarship database, collects up to 50 detail-page URLs via
`extract_urls()` (any link containing `detail=`), then fetches and extracts each one in a custom
`scrape()` override (`daad.py:53-93`). Each detail page corresponds to one scholarship — this is the
cleanest of the three adapters for structured extraction since DAAD detail pages are genuinely
semi-structured (label/value admissions-style sections), unlike MastersPortal's freer prose.

## Scope
- `services/ingestion/app/adapters/daad.py` (edited)
- New/extended adapter unit tests

## Implementation Steps
- [ ] Add a private `_extract_scholarship(main_content, url) -> Optional[dict]`, called from
      `extract_documents()` on the same `main_content` node it already isolates:
      - `provider`: constant `"DAAD"`.
      - `country`: `self.country` (already hardcoded `"Germany"` — reliable).
      - `name`: page title/heading (reliable — DAAD detail pages consistently title the scholarship).
      - `source_url`: the detail-page URL.
      - `degree_level`: DAAD listings vary by program type (research grants, full masters, PhD) —
        best-effort regex/keyword match against common headings ("Master's", "Doctoral", "Research
        Grant"); leave `None` when ambiguous rather than guessing.
      - `deadline`: regex over a labeled "Application deadline"/"Deadline" field, common on DAAD detail
        pages — parse to `date` when a clear day/month/year is found; leave `None` for rolling/
        unstated deadlines (do not fabricate a date).
      - `award_amount`: reuse the EUR-amount regex/normalization approach already proven in
        `german_embassy_cairo.py:20,49-72` (`_AMOUNT_EUR_RE`, European vs. US decimal/thousands-
        separator normalization) — DAAD stipend amounts are commonly stated in EUR. Store as free text
        (matching the `scholarship_programs.award_amount VARCHAR(255)` column), not a bare float,
        since award structures often combine a stipend + additional allowances in one paragraph.
      - `eligibility`: a JSON bag capturing whatever structured eligibility bullet points exist on the
        page (e.g. `{"items": [...]}`, matching the `visa_requirements` "items or summary" pattern from
        `german_embassy_cairo.py:172`) — do not invent a fixed eligibility schema beyond what the
        ticket's DDL specifies (`eligibility JSONB`).
      - `citizenship_eligible`: default `True` unless the page explicitly excludes certain nationalities
        (rare on DAAD pages relevant to this crawl) — leave the default rather than trying to parse
        nationality-exclusion lists in this initial implementation.
      - `min_gpa`, `min_ielts`: best-effort regex, `None` when not found.
      - Compute `content_hash` via the Task 07 shared helper before attaching it to the record.
- [ ] `extract_documents()`: attach `doc_dict["scholarship_programs"] = [record]` when a record is
      successfully extracted, `[]` otherwise — same list-shaped convention as Task 09/11.
- [ ] Add public `scrape_structured(self) -> list[dict]`: reuses the adapter's existing crawl logic
      (`daad.py:53-93`'s index-page-then-detail-page traversal) but returns only the flattened
      `scholarship_programs` records across all crawled detail pages.
- [ ] Do not change `extract_urls()`, the constructor, the existing `scrape()` override, or any
      existing chunk-shaped output field.

## Expected Files/Modules
- `services/ingestion/app/adapters/daad.py` (edited)
- Adapter test file (new or extended)

## Dependencies
- Task 07 (shared `compute_content_hash()` helper).

## Risks
- **Deadline format variance.** DAAD deadlines are stated inconsistently across scholarships (single
  date, date range, "rolling," cycle-dependent "check individual programme page") — the extraction
  must tolerate all of these by falling back to `None` rather than raising or guessing a date.
- **Award-amount reuse risk.** Directly copying `german_embassy_cairo.py`'s `_AMOUNT_EUR_RE`/
  `_extract_amount_eur` logic (rather than importing/sharing it) risks drift if one copy is later
  fixed and the other isn't — consider whether this amount-parsing helper should also move into a
  shared module (e.g. alongside Task 07's `content_hash.py`, or a new `app/core/extraction.py`).
  Flagged as an implementation-time judgment call, not mandated here, since the ticket doesn't ask for
  this refactor explicitly — a reasonable default is to share it if Task 11 (Chevening) also needs EUR/
  GBP amount parsing, otherwise duplicate minimally.
- **Volume**: up to 50 detail pages per run, each a candidate structured record — Task 12's
  per-record try/except isolation (inherited from the GOA-086 pattern) must hold at this volume
  without one bad record aborting the batch.

## Definition of Done
- `DAADAdapter.scrape_structured()` returns `scholarship_programs`-shaped records with correct
  `award_amount`/`deadline` when present in fixture HTML.
- `extract_documents()`/`scrape()`'s existing chunk-document output is unchanged for any input that
  produces no structured record.
- A fixture detail page with no identifiable deadline/award text still produces a valid record with
  those fields `None`, not a crash.
- Every emitted record has a `content_hash`.

## Acceptance Criteria
- Unit test: fixture HTML with a known deadline ("Application deadline: 15 October 2026") and award
  amount ("€850 per month") → `scrape_structured()` returns a record with the correct parsed
  `deadline` and `award_amount` text.
- Unit test: fixture HTML with a rolling/unstated deadline → record still returned with
  `deadline=None`, no exception.
- Regression test: existing `test_daad_adapter_extracts_content` (`tests/test_adapters.py`) passes
  unmodified.

## Notes for Implementation
- This task does not add an LLM extraction pass, matching Task 09's scoping decision — regex/DOM-only
  for v1.
- Coordinate with Task 12: this adapter's `"scholarship_programs"` dict key is what the orchestrator
  wiring must pop for this adapter, same key Task 11 (Chevening) also uses.
- Coordinate with Task 11 on the `award_amount` regex approach if it is factored into a shared helper
  — avoid two independently-drifting copies of EUR/GBP amount parsing.

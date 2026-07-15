# Task 11: `CheveningAdapter.scrape_structured()`

## Objective
Add structured `scholarship_programs` extraction to `CheveningAdapter`, exposed via a
`scrape_structured()` method, correctly capturing `deadline` and `award_amount` per the ticket's
explicit acceptance criterion — which requires fetching at least one additional page beyond the
adapter's current single target URL.

## Background
`services/ingestion/app/adapters/chevening.py` (31 lines) is the simplest of the three adapters: a
`BaseAdapter` (static httpx, not Playwright) subclass with a single `target_url`
(`https://www.chevening.org/scholarships/who-can-apply/`), no `extract_urls()`/detail-page crawl, and
`extract_documents()` that grabs `<main>` text and returns only the standard chunk dict.

**This is an eligibility page, not a deadlines/awards page.** Reading its content confirms it covers
eligibility criteria (country/degree/work-experience requirements), not application deadlines or
award composition (tuition/stipend/travel). Chevening publishes deadline information on a separate
timeline/key-dates page and award composition on a separate "what's included"/about page. Satisfying
this ticket's explicit unit-test acceptance criterion — `CheveningAdapter.scrape_structured()`
extracts correct `deadline` and `award_amount` — is not achievable from the current single-URL scrape
alone. This mirrors `GermanEmbassyCairoAdapter.scrape()`'s override pattern
(`german_embassy_cairo.py:208-253`), which already fetches a second document (a discovered PDF leaflet)
beyond its base target page — the same solution shape applies here: `scrape_structured()` (and,
correspondingly, an updated `scrape()`/`extract_documents()` flow) fetches a second, explicitly-named
URL for deadline/award content.

## Scope
- `services/ingestion/app/adapters/chevening.py` (edited)
- New/extended adapter unit tests

## Implementation Steps
- [ ] Confirm the actual Chevening page(s) that state deadline and award composition (see master
      plan's Open Questions #3 — this must be confirmed against the live site before writing fixture
      HTML, not assumed). Add a second constant URL (e.g. `TIMELINE_URL`/`AWARD_URL`) to the adapter
      alongside its existing `target_url`.
  - [ ] Since Chevening is effectively a single named scholarship (unlike DAAD's many), it is
      reasonable to hardcode `name="Chevening Scholarship"` and `degree_level="Master"` rather than
      parse them — confirm this against the ticket owner as a simplification, since Chevening is
      specifically a one-year taught master's scholarship.
- [ ] Add a private `_extract_scholarship(eligibility_content, deadline_content, url) -> Optional[dict]`
      (or two smaller helpers combined by the caller):
      - `provider`: constant `"Chevening"`.
      - `country`: `self.country` (already hardcoded `"UK"`).
      - `name`: constant `"Chevening Scholarship"` (see above).
      - `source_url`: the primary `target_url`.
      - `deadline`: parsed from the second fetched page's dated content (e.g. "Applications open in
        August and close in early November" — Chevening deadlines are annual and shift year to year;
        extract the specific stated date for the current cycle when present, `None` when the page only
        states a month/season without a specific day).
      - `award_amount`: Chevening's award is described in prose (full tuition, monthly stipend,
        economy return airfare, additional allowances) rather than a single figure — capture the
        relevant paragraph/section as free text (matching the `VARCHAR(255)` column and the ticket's
        own DDL comment that this field "varies: monthly stipend, full tuition"), possibly reusing the
        EUR/GBP amount-parsing approach from Task 10 if a shared helper was factored out there.
      - `eligibility`: JSON bag from the existing eligibility page content (the adapter's current
        target page is actually well-suited for this field, even though it doesn't have deadline/
        award data).
      - `citizenship_eligible`: default `True` (Chevening is explicitly open to Egyptian applicants;
        no exclusion logic needed for this adapter).
      - `min_gpa`, `min_ielts`: best-effort regex over the eligibility page content, `None` when not
        found.
      - Compute `content_hash` via the Task 07 shared helper.
- [ ] Update `extract_documents()`/`scrape()` (`BaseAdapter`'s default `scrape()` template method
      currently just fetches `target_url` once) to also fetch the second URL, following
      `GermanEmbassyCairoAdapter.scrape()`'s override pattern: fetch primary page, extract chunk +
      partial structured data, fetch secondary page, merge deadline/award fields into the structured
      record, attach `doc_dict["scholarship_programs"] = [record]`.
- [ ] Add public `scrape_structured(self) -> list[dict]`: runs the same two-page fetch, returns only
      the flattened `scholarship_programs` record(s).
- [ ] Preserve the existing single-chunk-document output shape for the primary page — do not turn the
      secondary deadline/award page into its own separate chunk document unless that's independently
      useful for the unstructured RAG pipeline (a reasonable secondary benefit, but not required by
      this ticket — confirm before adding scope).

## Expected Files/Modules
- `services/ingestion/app/adapters/chevening.py` (edited)
- Adapter test file (new or extended)

## Dependencies
- Task 07 (shared `compute_content_hash()` helper).
- Confirmation of the actual second Chevening URL (open question, blocks writing real fixtures, does
  not block writing the adapter code structure against a placeholder fixture).

## Risks
- **Real gap versus the ticket's implicit assumption.** The ticket's implementation notes say
  structured extraction "reuses each adapter's already-fetched HTML" — true for MastersPortal and
  DAAD, not fully true for Chevening as currently configured. This task requires an additional fetch,
  which is a deviation from a literal reading of the ticket's implementation notes (though it is
  faithful to the ticket's actual acceptance criteria, which explicitly require `deadline`/
  `award_amount` extraction). Flag this to the ticket owner rather than silently expanding the
  adapter's scope.
- **Annual deadline volatility.** Chevening's deadline changes every application cycle — this is
  naturally handled by `content_hash` detecting the change on each scrape (no special-casing needed),
  but the fixture used in the unit test will become stale/unrealistic over time; keep the fixture
  clearly synthetic rather than pinned to a specific real year's date to avoid the test implying a
  hardcoded expectation.
- **Second-page fetch failure.** If the secondary URL becomes unreachable or changes structure, the
  adapter should still produce its existing chunk-document output from the primary page (partial
  degradation, not total failure) — mirroring `german_embassy_cairo.py:220-223`'s handling of a
  missing/failed PDF discovery.

## Definition of Done
- `CheveningAdapter.scrape_structured()` returns a `scholarship_programs`-shaped record with correct
  `deadline` and `award_amount` from fixture HTML (ticket's explicit DoD wording).
- Primary-page chunk-document output is unchanged when the secondary fetch fails.
- Every emitted record has a `content_hash`.

## Acceptance Criteria
- Unit test: fixture HTML for both pages with known deadline and award-amount text →
  `scrape_structured()` returns a record with correctly parsed `deadline` and `award_amount` (ticket's
  explicitly named DoD test).
- Unit test: secondary-page fetch mocked to fail → adapter still returns its existing chunk document
  from the primary page without raising.
- Regression test: existing `test_chevening_adapter_extracts_content` (`tests/test_adapters.py`)
  passes unmodified.

## Notes for Implementation
- This task does not add an LLM extraction pass, matching Tasks 09/10's scoping decision.
- Coordinate with Task 12: this adapter's `"scholarship_programs"` dict key is what the orchestrator
  wiring must pop, same key Task 10 (DAAD) also uses.
- Raise the second-URL requirement explicitly during planning review/refinement rather than discovering
  it mid-implementation — it changes this adapter's network footprint (2 fetches instead of 1) and its
  `BaseAdapter` vs. needing an overridden `scrape()`, similar in kind to
  `GermanEmbassyCairoAdapter`'s PDF-fetch override.

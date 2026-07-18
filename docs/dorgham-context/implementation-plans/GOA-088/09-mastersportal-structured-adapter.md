# Task 09: `MastersPortalAdapter.scrape_structured()`

## Objective
Add structured `program_requirements` extraction to `MastersPortalAdapter`, exposed via a
`scrape_structured()` method as GOA-088's acceptance criteria explicitly name, while keeping the
existing chunk-document behavior of `scrape()`/`extract_documents()` completely unchanged.

## Background
`services/ingestion/app/adapters/masters_portal.py` (28 lines) currently does no structured extraction
at all: `extract_documents()` grabs `#UniversityProfile` (or `<main>`) and returns only
`{source, category, country, url, content}`. There is no ECTS/GPA/IELTS/citizenship parsing anywhere
in this file today — all of it is net-new for this task. The adapter is a `BasePlaywrightAdapter`
subclass targeting UK university profile pages
(`https://www.mastersportal.com/countries/1/united-kingdom.html` as the index,
`extract_urls()` following `/universities/\d+/` links).

GOA-086's `GermanEmbassyCairoAdapter` is the reference pattern: it builds a structured record
alongside the chunk `content` inside `extract_documents()`, attaches it under a dict key
(`"visa_requirements"`), and computes `content_hash` via the shared helper (Task 07) before
attaching it to the record. This task follows the same mechanism but must also expose a standalone
`scrape_structured()` method per the ticket's literal acceptance-criteria wording (its unit test is
named `MastersPortalAdapter.scrape_structured()`, tested directly against fixture HTML).

**Reconciling the two**: implement a private helper, e.g. `_extract_program_requirement(main_content,
url) -> dict | None`, called from both `extract_documents()` (which attaches its result under
`doc_dict["program_requirements"] = [record] if record else []`) and from the public
`scrape_structured()` (a thin wrapper that runs the same fetch+parse path as `scrape()` but returns
only the structured record(s), suitable for direct unit testing against static fixture HTML without
mocking the full Playwright fetch machinery). This keeps exactly one extraction code path — the dual-
write property (same scrape, two outputs) holds even though two public methods exist.

## Scope
- `services/ingestion/app/adapters/masters_portal.py` (edited)
- New/extended adapter unit tests (file location per Task 17's testing conventions)

## Implementation Steps
- [ ] Add a private `_extract_program_requirement(main_content, url) -> Optional[dict]` that pulls,
      from the already-parsed `main_content` BeautifulSoup node (the same node `extract_documents()`
      already isolates via `soup.find(id="UniversityProfile") or soup.find("main")`):
      - `university`: page title/heading text (reliable — MastersPortal profile pages consistently
        name the university in a heading).
      - `country`: `self.country` (already hardcoded `"UK"` on this adapter's constructor — reliable,
        no parsing needed).
      - `degree_level`: from the URL path or a page heading/breadcrumb (e.g. "MSc"/"Master") —
        moderately reliable; may need a small controlled vocabulary mapping ("MSc"/"MA"/"MRes" →
        `"Master"`) rather than free-text passthrough, to keep the value consistent with the existing
        3 seed rows' `"Master"` convention.
      - `min_ects`: regex over the admissions-requirements section text for an explicit ECTS credit
        count (e.g. `r"(\d+)\s*ECTS"`) — **not reliably present on every page**; leave `None` when not
        found, never guess.
      - `min_gpa`, `min_ielts`, `required_citizenship`: **not reliably regex-extractable** — these are
        typically embedded in prose admissions paragraphs rather than consistent label/value pairs.
        For the initial (regex/DOM-only) implementation, extract via best-effort regex
        (`min_ielts` from patterns like `r"IELTS[:\s]+(\d\.\d)"`) and leave `None` when no match,
        rather than blocking on the LLM-extraction pass described in the ticket's implementation notes
        (see master plan's Open Questions — LLM extraction is treated as optional fast-follow scope,
        not a hard requirement for this task's Definition of Done).
      - `source_url`: the page URL passed into `extract_documents`.
      - Compute `content_hash` via `compute_content_hash()` (Task 07) over the record dict before
        attaching `content_hash` as a field on it, matching `german_embassy_cairo.py:168-188`'s
        pattern.
      - Return `None` (not an empty dict) when no university name can be identified at all, so the
        caller can skip attaching an empty/garbage record.
- [ ] `extract_documents()`: after building the existing chunk dict, call
      `_extract_program_requirement(main_content, url)`; if not `None`, attach it as
      `doc_dict["program_requirements"] = [record]` (list, for consistency with GOA-086's
      `"visa_requirements"` list-shaped key, even though MastersPortal only ever yields one record per
      page).
- [ ] Add public `scrape_structured(self) -> list[dict]`: runs the same fetch (`fetch_page` via the
      inherited Playwright machinery) and crawl (`extract_urls`) as `scrape()`, but returns only the
      flattened `program_requirements` records extracted from each page, for direct testability.
- [ ] Do not change `extract_urls()`, the constructor, or any existing chunk-shaped output field.

## Expected Files/Modules
- `services/ingestion/app/adapters/masters_portal.py` (edited)
- Adapter test file (new or extended, e.g. `services/ingestion/tests/test_masters_portal_structured.py`
  or appended to `tests/test_adapters.py`, per Task 17's final convention)

## Dependencies
- Task 07 (shared `compute_content_hash()` helper).

## Risks
- **Field reliability varies significantly by university.** MastersPortal aggregates listings from
  many universities with inconsistent page structure — `min_ects` in particular may be entirely absent
  on many profile pages. The extraction must degrade gracefully (fields stay `None`) rather than raise
  or fabricate values; a page with zero identifiable structured fields beyond `university`/`country`/
  `degree_level` is still a valid (if sparse) record.
- **`degree_level` normalization.** Free-text degree-level strings from the page ("MSc in Computer
  Science" vs. "Master of Science") risk producing values that never match anything a hard-gate
  comparison expects (`gates.py:13-15` does an exact string comparison against
  `program.degree_level`). Some normalization (mapping to `"Master"`/`"Bachelor"`/`"PhD"`, matching the
  3 existing seed rows' convention) is needed — flag as an implementation decision to confirm rather
  than silently picking a mapping that might not match GOA-012's expectations.
- **Multiple structured records per crawl vs. per page.** `scrape_structured()`'s crawl will visit many
  university pages in one run — confirm the caller (Task 12) expects a flat `list[dict]` across all
  crawled pages, not one list per page.

## Definition of Done
- `MastersPortalAdapter.scrape_structured()` returns a `program_requirements`-shaped record with
  correct `min_ects`/`min_ielts` when present in fixture HTML (ticket's explicit DoD wording).
- `extract_documents()` / `scrape()`'s existing chunk-document output is byte-for-byte unchanged for
  any input that produces no structured record (regression safety).
- A fixture page with no identifiable ECTS/IELTS values still produces a valid record with those
  fields as `None`, not a crash.
- Every emitted record has a `content_hash` computed via the Task 07 shared helper.

## Acceptance Criteria
- Unit test: fixture HTML with known ECTS ("120 ECTS credits") and IELTS ("IELTS: 6.5") values →
  `scrape_structured()` returns a record with `min_ects=120`, `min_ielts=6.5` (ticket's explicitly
  named DoD test).
- Unit test: fixture HTML with no admissions-requirements section → record still returned (or `[]` if
  no university name is identifiable at all), no exception raised.
- Regression test: existing `test_masters_portal_adapter_extracts_content` (`tests/test_adapters.py`)
  passes unmodified.

## Notes for Implementation
- This task does not add an LLM extraction pass — per the master plan's Open Questions, the initial
  implementation is regex/DOM-only, matching GOA-086's actual (not just described) approach. If the
  ticket owner confirms LLM extraction is required for v1, that is materially more work (API
  integration, prompt design, cost/latency impact) and should be re-scoped as its own task rather than
  folded into this one.
- Coordinate with Task 12: this adapter's `"program_requirements"` dict key (not
  `"scholarship_programs"`) is what the orchestrator wiring must pop for this specific adapter.

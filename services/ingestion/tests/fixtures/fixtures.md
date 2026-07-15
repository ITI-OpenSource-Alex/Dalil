# Fixture provenance

Tracks where each fixture under `tests/fixtures/` came from, so a fixture can be
refreshed or trusted without having to re-derive its origin from git blame. Update
this file whenever a fixture is added, replaced, or re-captured from a live page.

## daad/

| File | Origin | Notes |
|---|---|---|
| `detail_page_full.html` | Hand-built from GOA-088 Task 10's real investigation excerpts (not a live capture) | Happy-path page: clear deadline, EUR-prefixed amount, IELTS/GPA present, single-entry eligibility list. |
| `detail_page_rolling_deadline.html` | Hand-built from GOA-088 Task 10's real investigation excerpts | Edge case: rolling/unparseable deadline, number-before-currency amount wording ("992 euros a month"), no degree/IELTS/GPA signals. |
| `detail_page_no_structured_sections.html` | Hand-built | Edge case: no recognizable section headings at all -- every optional field must resolve to `None`/`{}` without crashing. |
| `detail_page_no_title_no_h1.html` | Hand-built | Edge case: no `<title>` and no `<h1>` -- `name` can't be resolved, so no `scholarship_programs` record should be emitted. |
| `real_scholarship_detail_50026200.html` | **Verbatim live capture** -- `https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database.pdf?detail=50026200` ("Study Scholarships - Master Studies for All Academic Disciplines"), retrieved via WebFetch/WebSearch during Task 10's live-verification follow-up (www2.daad.de was returning a persistent 403 to direct requests from this environment at the time). This fixture caught two real extraction bugs (degree_level picking a prerequisite degree instead of the awarded one; section-boundary bleed-through on award_amount/eligibility) that the hand-built fixtures above did not surface. |

## mastersportal/

| File | Origin | Notes |
|---|---|---|
| `university_page.html` | Hand-built, modeled on the real University of Oxford profile page structure observed during Task 09's live investigation | Used for `/studies/` link discovery tests. |
| `programme_page_with_ects.html` | Hand-built | Happy-path page with both ECTS and IELTS present, satisfying the ticket's literal min_ects/min_ielts acceptance criterion. |
| `programme_page_no_ects.html` | Modeled directly on the real Applied Theology (University of Oxford) programme page's structure, `https://www.mastersportal.com/studies/77603/applied-theology.html`, observed during Task 09's live investigation | Matches the real page: GPA resolves to a non-numeric UK classification ("Upper Second Class"), no ECTS figure appears anywhere (credits are stated in a different, non-ECTS scheme instead). |

## Maintenance

- When a live smoke test (`live_test.py`, run manually) finds that real page structure no longer matches a fixture here, that's a bug report: update the fixture from the real page *and* re-verify the extraction logic against it in the same change, per the GOA-088 testing strategy plan.
- Prefer capturing a real page over hand-writing a new one where practical -- the one verbatim DAAD capture above is what caught real bugs the hand-built fixtures missed.

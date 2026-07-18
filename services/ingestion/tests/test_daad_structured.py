"""
GOA-088 Task 10 -- unit tests for DAADAdapter's structured scholarship_programs
extraction.

Fixture HTML lives under tests/fixtures/daad/ (see fixtures.md there for
provenance of each file) and models real DAAD content two ways:
  - detail_page_full.html / detail_page_rolling_deadline.html / etc. model the
    section text excerpts supplied for this task plus the adapter's existing
    DOM-selector conventions (www2.daad.de was returning a persistent 403 to
    every request -- curl, plain `requests`, and Playwright alike -- from this
    environment's network when this adapter was first implemented, so live
    verification wasn't initially possible; see Task 10's follow-up
    investigation report).
  - real_scholarship_detail_50026200.html is transcribed directly from a real,
    live DAAD scholarship page (detail=50026200, "Study Scholarships - Master
    Studies for All Academic Disciplines"), retrieved via WebFetch/WebSearch --
    a different network path than this environment's own blocked egress IP.
    This fixture is what caught two real bugs during verification (degree_level
    picking a prerequisite degree instead of the awarded one, and
    section-boundary bleed-through on award_amount/eligibility) -- both fixed,
    and locked in as regression tests here.
"""
from pathlib import Path

import pytest

from app.adapters.daad import DAADAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "daad"

DAAD_DETAIL_FULL_HTML = (FIXTURES_DIR / "detail_page_full.html").read_text(encoding="utf-8")

# Models the prompt's real investigation excerpts: rolling/unparseable deadline,
# a differently-worded value section ("Interns are usually paid / 992 euros a
# month"), and no degree/IELTS/GPA signals anywhere on the page.
DAAD_DETAIL_ROLLING_DEADLINE_HTML = (FIXTURES_DIR / "detail_page_rolling_deadline.html").read_text(encoding="utf-8")

DAAD_DETAIL_NO_STRUCTURED_SECTIONS_HTML = (FIXTURES_DIR / "detail_page_no_structured_sections.html").read_text(encoding="utf-8")

DAAD_DETAIL_NO_TITLE_NO_H1_HTML = (FIXTURES_DIR / "detail_page_no_title_no_h1.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _extract_scholarship() / extract_documents() -- structured field extraction
# ---------------------------------------------------------------------------

def test_extract_documents_extracts_correct_deadline_and_award_amount():
    """Ticket's explicit unit-test acceptance criterion: fixture HTML with a
    known deadline ("Application deadline: 15 October 2026") and award amount
    ("850 EUR per month" -- prompt's real-world number-before-currency ordering)
    -> scrape_structured()-equivalent record has correctly parsed deadline and
    award_amount text."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_FULL_HTML, url="https://www2.daad.de/detail=12345")

    assert len(docs) == 1
    records = docs[0]["scholarship_programs"]
    assert len(records) == 1
    record = records[0]

    assert record["name"] == "Helmut-Schmidt-Programme"
    assert record["provider"] == "DAAD"
    assert record["country"] == "Germany"
    assert record["source_url"] == "https://www2.daad.de/detail=12345"
    assert record["deadline"].isoformat() == "2026-10-15"
    assert "850 EUR per month" in record["award_amount"]
    assert record["content_hash"]


def test_extract_documents_extracts_degree_level_ielts_and_gpa():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_FULL_HTML, url="https://www2.daad.de/detail=12345")
    record = docs[0]["scholarship_programs"][0]

    assert record["degree_level"] == "Master"
    assert record["min_ielts"] == 7.5
    assert record["min_gpa"] == 3.0


def test_extract_documents_extracts_eligibility_as_items_list():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_FULL_HTML, url="https://www2.daad.de/detail=12345")
    record = docs[0]["scholarship_programs"][0]

    assert record["eligibility"] == {
        "items": ["Graduates of German universities", "Applicants under 32 years old"]
    }


def test_extract_documents_defaults_citizenship_eligible_to_true():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_FULL_HTML, url="https://www2.daad.de/detail=12345")
    record = docs[0]["scholarship_programs"][0]

    assert record["citizenship_eligible"] is True


# ---------------------------------------------------------------------------
# Edge cases from manual investigation
# ---------------------------------------------------------------------------

def test_rolling_deadline_yields_none_not_a_guessed_date():
    """Ticket's explicit unit-test acceptance criterion: fixture HTML with a
    rolling/unstated deadline -> record still returned with deadline=None, no
    exception."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_ROLLING_DEADLINE_HTML, url="https://www2.daad.de/detail=99")
    record = docs[0]["scholarship_programs"][0]

    assert record["deadline"] is None


def test_number_before_currency_award_amount_is_still_detected():
    """Real DAAD phrasing ("992 euros a month") states the amount before the
    currency word -- must still be detected and stored as free text, not reduced
    to a bare float."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_ROLLING_DEADLINE_HTML, url="https://www2.daad.de/detail=99")
    record = docs[0]["scholarship_programs"][0]

    assert record["award_amount"] is not None
    assert "992 euros a month" in record["award_amount"]
    assert isinstance(record["award_amount"], str)


def test_missing_ielts_and_gpa_yield_none_not_fabricated():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_ROLLING_DEADLINE_HTML, url="https://www2.daad.de/detail=99")
    record = docs[0]["scholarship_programs"][0]

    assert record["min_ielts"] is None
    assert record["min_gpa"] is None


def test_ambiguous_degree_level_yields_none():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_ROLLING_DEADLINE_HTML, url="https://www2.daad.de/detail=99")
    record = docs[0]["scholarship_programs"][0]

    assert record["degree_level"] is None


def test_no_recognizable_sections_still_produces_valid_record_with_none_fields():
    """Definition of Done: a fixture detail page with no identifiable
    deadline/award text still produces a valid record with those fields None,
    not a crash."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        DAAD_DETAIL_NO_STRUCTURED_SECTIONS_HTML, url="https://www2.daad.de/detail=55"
    )

    records = docs[0]["scholarship_programs"]
    assert len(records) == 1
    record = records[0]
    assert record["name"] == "Unlabelled Scholarship"
    assert record["deadline"] is None
    assert record["award_amount"] is None
    assert record["eligibility"] == {}
    assert record["degree_level"] is None
    assert record["min_ielts"] is None
    assert record["min_gpa"] is None
    assert record["content_hash"]


def test_missing_name_yields_no_scholarship_record():
    """(provider, name) is scholarship_programs' upsert key -- a record missing
    the name can't be upserted, so it must not be emitted even though the page
    has real structured content."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(DAAD_DETAIL_NO_TITLE_NO_H1_HTML, url="https://www2.daad.de/detail=77")

    assert docs[0]["scholarship_programs"] == []


# ---------------------------------------------------------------------------
# Real live-content verification (see module docstring) -- transcribed from
# https://www2.daad.de/.../21148-scholarship-database.pdf?detail=50026200
# ---------------------------------------------------------------------------

REAL_SCHOLARSHIP_DETAIL_HTML = (FIXTURES_DIR / "real_scholarship_detail_50026200.html").read_text(encoding="utf-8")


def test_real_scholarship_page_name_strips_bullet_daad_suffix():
    """Regression for a real bug: the live title separator is "•" (bullet),
    not "-"/"|" as originally assumed -- confirmed against the real page."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    assert record["name"] == "Study Scholarships - Master Studies for All Academic Disciplines"


def test_real_scholarship_page_degree_level_prefers_title_over_prerequisite_mention():
    """Regression for a real bug: the real page's eligibility section states a
    PREREQUISITE degree ("Bachelor's or Diplom") earlier in the document than the
    funding description states the degree actually AWARDED ("Master's degree
    programme") -- a naive earliest-occurrence text scan incorrectly returned
    "Bachelor" for this scholarship, whose title correctly says "Master Studies"."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    assert record["degree_level"] == "Master"


def test_real_scholarship_page_award_amount_stops_at_selection_boundary():
    """Regression for a real bug: without "Selection" (and other real headings)
    in the section-boundary set, award_amount bled past its own section into the
    next one and was truncated mid-sentence at the 255-char cap."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    assert "992 euros a month" in record["award_amount"]
    assert "Annually study allowance" in record["award_amount"]
    assert "selection committee" not in record["award_amount"].lower()


def test_real_scholarship_page_eligibility_stops_before_funding_section():
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    items = record["eligibility"]["items"]
    assert any("completed your first degree" in item for item in items)
    assert not any("postgraduate or Master's degree programme" in item for item in items)


def test_real_scholarship_page_deadline_is_none_for_updated_annually_wording():
    """The real page's "Application deadline" section has no specific calendar
    date ("updated annually... find the current dates here") -- must not be
    confused with the unrelated "1 October 2027" funding-start date mentioned
    elsewhere on the page, outside the deadline section."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    assert record["deadline"] is None


def test_real_scholarship_page_ielts_and_gpa_are_none():
    """The real page lists IELTS only as one of several accepted test types with
    no minimum score, and never uses the term "GPA" at all (DAAD refers to
    "grades"/"degree" instead) -- both must stay None, not fabricated."""
    adapter = DAADAdapter()
    docs = adapter.extract_documents(
        REAL_SCHOLARSHIP_DETAIL_HTML,
        url="https://www2.daad.de/deutschland/stipendium/datenbank/en/21148-scholarship-database/?detail=50026200",
    )
    record = docs[0]["scholarship_programs"][0]

    assert record["min_ielts"] is None
    assert record["min_gpa"] is None


# ---------------------------------------------------------------------------
# Regression: existing chunk-document behavior unchanged
# ---------------------------------------------------------------------------

def test_extract_documents_backward_compatible_content_extraction():
    """Regression: matches tests/test_adapters.py::test_daad_adapter_extracts_content
    exactly -- the pre-existing call shape and chunk content must be unaffected."""
    mock_html = '<html><body><main>DAAD Scholarship Info</main></body></html>'
    adapter = DAADAdapter()
    docs = adapter.extract_documents(mock_html)

    assert len(docs) == 1
    assert "DAAD Scholarship Info" in docs[0]["content"]
    assert docs[0]["source"] == "daad"
    assert docs[0]["category"] == "scholarships"
    assert docs[0]["country"] == "Germany"


def test_extract_documents_still_returns_scholarship_programs_key_when_no_name_found():
    """The new key is always present (possibly empty), never a KeyError for
    callers that assume it exists once Task 12 wires the orchestrator's pop()."""
    mock_html = '<html><body><main>DAAD Scholarship Info</main></body></html>'
    adapter = DAADAdapter()
    docs = adapter.extract_documents(mock_html)

    assert docs[0]["scholarship_programs"] == []


# ---------------------------------------------------------------------------
# scrape_structured()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scrape_structured_flattens_records_across_documents(mocker):
    adapter = DAADAdapter()

    mocker.patch.object(
        adapter,
        "scrape",
        return_value=[
            {"content": "no structured data here", "scholarship_programs": []},
            {
                "content": "a real scholarship page",
                "scholarship_programs": [{"provider": "DAAD", "name": "Helmut-Schmidt-Programme"}],
            },
        ],
    )

    records = await adapter.scrape_structured()

    assert records == [{"provider": "DAAD", "name": "Helmut-Schmidt-Programme"}]

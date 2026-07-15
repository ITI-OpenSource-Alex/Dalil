"""
GOA-088 Task 09 -- unit tests for MastersPortalAdapter's programme-page discovery
and structured program_requirements extraction.

Fixture HTML lives under tests/fixtures/mastersportal/ (see fixtures.md there for
provenance of each file). programme_page_no_ects.html in particular mirrors the
real line-by-line <main> structure observed on a live MastersPortal programme page
(Applied Theology MTh, University of Oxford,
https://www.mastersportal.com/studies/77603/applied-theology.html) during manual
verification: each "line" BeautifulSoup's get_text(separator="\\n") produces is
modeled as its own element, since the extraction logic in masters_portal.py depends
on that line-per-element structure to skip descriptive paragraphs between a label
and its value.
"""
from pathlib import Path

import pytest

from app.adapters.masters_portal import MastersPortalAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mastersportal"

UNIVERSITY_PAGE_HTML = (FIXTURES_DIR / "university_page.html").read_text(encoding="utf-8")

# Models a programme page with BOTH IELTS and ECTS present, satisfying the ticket's
# literal acceptance criterion ("extracts a program_requirements row with correct
# min_ects/min_ielts from fixture HTML").
PROGRAMME_PAGE_WITH_ECTS_HTML = (FIXTURES_DIR / "programme_page_with_ects.html").read_text(encoding="utf-8")

# Models the real Oxford Applied Theology page: GPA resolves to a non-numeric UK
# classification, and no ECTS line exists anywhere on the page at all.
PROGRAMME_PAGE_NO_ECTS_HTML = (FIXTURES_DIR / "programme_page_no_ects.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# extract_programme_urls() -- discovering /studies/ links from a university page
# ---------------------------------------------------------------------------

def test_extract_programme_urls_discovers_studies_links():
    adapter = MastersPortalAdapter()
    urls = adapter.extract_programme_urls(UNIVERSITY_PAGE_HTML)

    assert urls == [
        "https://www.mastersportal.com/studies/77603/applied-theology.html",
        "https://www.mastersportal.com/studies/83079/theology.html",
    ]


def test_extract_programme_urls_deduplicates():
    adapter = MastersPortalAdapter()
    urls = adapter.extract_programme_urls(UNIVERSITY_PAGE_HTML)

    assert urls.count("https://www.mastersportal.com/studies/77603/applied-theology.html") == 1


def test_extract_programme_urls_ignores_university_links():
    adapter = MastersPortalAdapter()
    urls = adapter.extract_programme_urls(UNIVERSITY_PAGE_HTML)

    assert not any("/universities/" in u for u in urls)


def test_extract_urls_still_only_matches_universities_not_studies():
    """Regression: extract_urls() (country -> university hop) must remain
    unaffected by the new /studies/ pattern -- the two discovery methods are
    independent, each used at a different crawl tier."""
    adapter = MastersPortalAdapter()
    urls = adapter.extract_urls(UNIVERSITY_PAGE_HTML)

    assert urls == ["https://www.mastersportal.com/universities/35/university-of-oxford.html"]


# ---------------------------------------------------------------------------
# scrape_structured() / extract_documents() -- structured field extraction
# ---------------------------------------------------------------------------

def test_extract_documents_on_programme_page_extracts_correct_ects_and_ielts():
    """Ticket's explicit unit-test acceptance criterion: MastersPortalAdapter
    extracts a program_requirements row with correct min_ects/min_ielts from
    fixture HTML."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_PAGE_WITH_ECTS_HTML,
        url="https://www.mastersportal.com/studies/77603/applied-theology.html",
        university="University of Oxford",
    )

    assert len(docs) == 1
    records = docs[0]["program_requirements"]
    assert len(records) == 1
    record = records[0]

    assert record["university"] == "University of Oxford"
    assert record["country"] == "UK"
    assert record["degree_level"] == "Master"
    assert record["min_ects"] == 120
    assert record["min_ielts"] == 7.5
    assert record["content_hash"]


def test_extract_documents_leaves_gpa_none_when_value_is_non_numeric_classification():
    """The real Oxford page states a UK degree classification ("Upper Second
    Class") where a numeric GPA would otherwise be -- this must not be fabricated
    into a numeric min_gpa."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_PAGE_NO_ECTS_HTML,
        url="https://www.mastersportal.com/studies/77603/applied-theology.html",
        university="University of Oxford",
    )

    record = docs[0]["program_requirements"][0]
    assert record["min_gpa"] is None
    assert record["min_ielts"] == 7.5


def test_extract_documents_leaves_ects_none_when_absent_from_page():
    """Matches the real, verified Oxford Applied Theology page: no ECTS figure is
    stated anywhere (credits are given in a non-ECTS scheme instead) -- min_ects
    must stay None rather than being derived from the unrelated credit total."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_PAGE_NO_ECTS_HTML,
        url="https://www.mastersportal.com/studies/77603/applied-theology.html",
        university="University of Oxford",
    )

    record = docs[0]["program_requirements"][0]
    assert record["min_ects"] is None


def test_extract_documents_returns_no_program_requirements_key_without_university_name():
    """(university, degree_level, country) is the upsert key -- a record missing
    the university name can't be upserted, so it must not be emitted at all."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_PAGE_WITH_ECTS_HTML,
        url="https://www.mastersportal.com/studies/77603/applied-theology.html",
        university=None,
    )

    assert "program_requirements" not in docs[0]


def test_extract_documents_on_university_page_has_no_program_requirements_key():
    """A university-profile-page URL (not /studies/) must never produce a
    program_requirements record, even though this fixture also links to
    programme pages within its body."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        UNIVERSITY_PAGE_HTML,
        url="https://www.mastersportal.com/universities/35/university-of-oxford.html",
    )

    assert "program_requirements" not in docs[0]


def test_extract_documents_backward_compatible_without_url_or_university_args():
    """Regression: the pre-existing call shape (positional html only, matching
    tests/test_adapters.py::test_masters_portal_adapter_extracts_content) must
    keep working unchanged."""
    mock_html = '<html><body><main>UK Computer Science Masters</main></body></html>'
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(mock_html)

    assert len(docs) == 1
    assert "UK Computer Science Masters" in docs[0]["content"]
    assert "program_requirements" not in docs[0]


# ---------------------------------------------------------------------------
# scrape_structured() -- full method exists and returns a flattened list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scrape_structured_flattens_records_across_documents(mocker):
    adapter = MastersPortalAdapter()

    mocker.patch.object(
        adapter,
        "scrape",
        return_value=[
            {"content": "uni page", "program_requirements": []},
            {
                "content": "programme page",
                "program_requirements": [{"university": "University of Oxford", "degree_level": "Master"}],
            },
        ],
    )

    records = await adapter.scrape_structured()

    assert records == [{"university": "University of Oxford", "degree_level": "Master"}]

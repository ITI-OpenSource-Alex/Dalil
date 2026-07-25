"""GOA-111 fix round: API-driven discovery scope, card-first extraction, status contract.

These tests exist because the previous HTML-scraping discovery harvested the search
page's unfiltered "featured programmes" module — Udacity / Flinders / paramedicine
rows labeled country='Europe' landed in program_requirements. Each test below pins
one of the behaviors that prevented recurrence.
"""

import pytest

from app.adapters.masters_portal import (
    DISCIPLINE_IDS,
    EUROPE_ISO,
    MastersPortalAdapter,
    _as_number,
    _card_field,
    _normalize_degree_level,
)


def _card(iso="DE", title="Data Engineering", uni="TU Munich",
          url="/studies/123456/data-engineering.html", ielts=6.5, ects=120):
    """Minimal card in the search API's nested {'func': ...} shape."""
    return {
        "getId": 123456,
        "getTitle": title,
        "getDegree": "M.Sc.",
        "getCountryIsoCode": iso,
        "getEcts": ects,
        "getGPA": None,
        "getWorkExperienceYears": None,
        "getEnglishRequirements": {"class": "IEnglishRequirements", "func": {"getIELTS": ielts}},
        "getProgrammeLink": {"class": "IInternalLink", "func": {"getUrl": url}},
        "getUniversityLink": {"class": "ILinkForVirtualEntity", "func": {"getDescription": uni}},
    }


PROGRAMME_HTML = """
<html><head><title>M.Sc. at TU Munich | MastersPortal</title></head>
<body><main>
  <h1>Data Engineering</h1>
  application deadline
  31 May 2026
</main></body></html>
"""


def test_discipline_ids_are_the_verified_sitemap_ids():
    # sitemaps/disciplines.xml: /disciplines/7/engineering-technology.html,
    # /disciplines/24/computer-science-it.html — a change here means the
    # mapping must be re-verified against the live sitemap, not guessed.
    assert DISCIPLINE_IDS == {"engineering": 7, "computer_science": 24}


def test_card_scope_rejects_non_european_iso():
    adapter = MastersPortalAdapter()
    assert adapter.card_in_scope(_card(iso="DE"))
    assert adapter.card_in_scope(_card(iso="GB"))
    # The exact offenders from the polluted crawl: US (Udacity/Colorado State),
    # AU (Flinders), MY (Sunway).
    for iso in ("US", "AU", "MY", None):
        assert not adapter.card_in_scope(_card(iso=iso))


def test_card_to_url_is_absolute_and_normalized():
    adapter = MastersPortalAdapter()
    url = adapter.card_to_url(_card(url="/studies/123456/data-engineering.html"))
    assert url == "https://www.mastersportal.com/studies/123456/data-engineering.html"
    # URL variants dedupe to one canonical form
    variant = adapter.card_to_url(_card(url="/studies/123456/data-engineering.html?utm_source=x"))
    assert variant == url


def test_card_first_extraction_prefers_api_fields():
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_HTML,
        url="https://www.mastersportal.com/studies/123456/data-engineering.html",
        card=_card(),
    )
    record = docs[0]["program_requirements"][0]
    assert record["country"] == "Germany"          # ISO-mapped, never 'Europe'
    assert record["university"] == "TU Munich"
    assert record["program_name"] == "Data Engineering"
    assert record["min_ielts"] == 6.5              # from the card, not the page
    assert record["min_ects"] == 120
    assert record["deadline"] == "2026-05-31"      # page-parsed — not in the card


def test_quality_gate_rejects_region_literal_country():
    adapter = MastersPortalAdapter()
    # No card, and a page whose only country signal is the region literal:
    html = "<html><body><main><h1>X</h1><a class='UniversityLink'>U</a>Study in Europe</main></body></html>"
    docs = adapter.extract_documents(html, url="https://www.mastersportal.com/studies/1/x.html")
    assert "program_requirements" not in docs[0]


def test_title_doubling_collapsed():
    adapter = MastersPortalAdapter()
    html = ("<html><body><main><span class='StudyTitle'>Generative AIGenerative AI</span>"
            "<a class='UniversityLink'>U</a>Study in Germany</main></body></html>")
    docs = adapter.extract_documents(html, url="https://www.mastersportal.com/studies/2/y.html")
    assert docs[0]["program_requirements"][0]["program_name"] == "Generative AI"


@pytest.mark.asyncio
async def test_scrape_marks_extracted_not_scraped(mocker):
    """The adapter must never claim 'scraped' — that promotion belongs to the
    handler after a successful RAG upsert (retry semantics depend on it)."""
    adapter = MastersPortalAdapter()
    card = _card()
    mocker.patch.object(adapter, "discover_page",
                        side_effect=[([card], 1), ([], 1)])
    mocker.patch.object(adapter, "fetch_page", return_value=PROGRAMME_HTML)
    mocker.patch("app.adapters.masters_portal.polite_delay")
    mocker.patch("app.adapters.masters_portal.robot_checker").is_allowed.return_value = True
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 1, "scroll_offset": 0, "exhausted": False}
    state.is_url_scraped.return_value = False

    docs = await adapter.scrape(per_run_cap_per_discipline=5)

    assert any(d.get("program_requirements") for d in docs)
    statuses = [c.args[3] for c in state.mark_url_status.call_args_list]
    assert "extracted" in statuses
    assert "scraped" not in statuses


@pytest.mark.asyncio
async def test_scrape_skips_out_of_scope_cards_without_fetching(mocker):
    adapter = MastersPortalAdapter()
    us_card = _card(iso="US", url="/studies/9/us-prog.html")
    mocker.patch.object(adapter, "discover_page", side_effect=[([us_card], 1), ([], 1)])
    fetch = mocker.patch.object(adapter, "fetch_page")
    mocker.patch("app.adapters.masters_portal.polite_delay")
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 1, "scroll_offset": 0, "exhausted": False}
    state.is_url_scraped.return_value = False

    docs = await adapter.scrape(per_run_cap_per_discipline=5)

    assert docs == []
    fetch.assert_not_called()  # out-of-scope programs cost zero page fetches


@pytest.mark.asyncio
async def test_scrape_resumes_from_saved_offset(mocker):
    """Discovery must continue from the persisted scroll_offset, not offset 0."""
    adapter = MastersPortalAdapter()
    seen_offsets = []

    async def fake_discover(discipline_id, offset):
        seen_offsets.append(offset)
        return [], 100  # empty page -> exhausts immediately

    mocker.patch.object(adapter, "discover_page", side_effect=fake_discover)
    mocker.patch("app.adapters.masters_portal.polite_delay")
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 3, "scroll_offset": 40, "exhausted": False}
    state.is_url_scraped.return_value = False

    await adapter.scrape(per_run_cap_per_discipline=5)

    assert all(off == 40 for off in seen_offsets)


def test_uk_honours_gpa_object_becomes_null_not_a_guess():
    """Live regression: every UK program 422'd because getGPA is an
    IGPARequirement object whose score is a grade class ('2_2'), not a float."""
    uk_gpa = {"class": "IGPARequirement",
              "func": {"getScale": "uk_honours", "getScore": "2_2", "isRequired": True}}
    assert _as_number(uk_gpa) is None

    adapter = MastersPortalAdapter()
    card = _card()
    card["getGPA"] = uk_gpa
    docs = adapter.extract_documents(
        PROGRAMME_HTML,
        url="https://www.mastersportal.com/studies/123456/data-engineering.html",
        card=card,
    )
    record = docs[0]["program_requirements"][0]
    assert record["min_gpa"] is None            # null, never invented
    assert record["program_name"] == "Data Engineering"  # program still retained


def test_degree_level_normalized_to_gate_vocabulary():
    """Live regression: display degrees ('M.Sc.', 'M.A.', 'Pre-Master') blocked 33 of
    46 programs at the exact-match degree_level gate. Canonical vocabulary only."""
    assert _normalize_degree_level("master") == "Master"
    assert _normalize_degree_level("M.Sc.") == "Master"
    assert _normalize_degree_level("MSc") == "Master"
    assert _normalize_degree_level("M.Eng.") == "Master"
    assert _normalize_degree_level("Pre-Master") == "Master"
    assert _normalize_degree_level("bachelor") == "Bachelor"
    assert _normalize_degree_level("PhD") == "PhD"
    assert _normalize_degree_level("") is None
    assert _normalize_degree_level(None) is None

    adapter = MastersPortalAdapter()
    card = _card()
    card["getLevel"] = "master"
    card["getDegree"] = "M.Sc."
    docs = adapter.extract_documents(
        PROGRAMME_HTML,
        url="https://www.mastersportal.com/studies/123456/data-engineering.html",
        card=card,
    )
    assert docs[0]["program_requirements"][0]["degree_level"] == "Master"


def test_as_number_coercions():
    assert _as_number(60) == 60.0
    assert _as_number(6.5) == 6.5
    assert _as_number("3.4") == 3.4
    assert _as_number({"class": "IGPARequirement", "func": {"getScore": 3.2}}) == 3.2
    for bad in (None, True, "upper second class", {}, {"func": {"getScore": "2_1"}}, []):
        assert _as_number(bad) is None


def test_card_field_walks_nested_func_shape():
    card = _card()
    assert _card_field(card, "getEnglishRequirements", "getIELTS") == 6.5
    assert _card_field(card, "getUniversityLink", "getDescription") == "TU Munich"
    assert _card_field(card, "missing", "path") is None

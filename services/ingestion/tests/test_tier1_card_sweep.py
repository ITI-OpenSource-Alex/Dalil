"""Option B Tier 1: build the catalog from API cards, with no page fetch.

A page fetch costs ~10 seconds, so covering the ~20,000 in-scope European
Engineering/CS programs that way is ~55 hours — impossible inside any bounded worker
and the reason GOA-041's "entire configured catalog within platform runtime limits"
was unachievable as written. Tier 1 uses only the search API's cards.
"""

import pytest

from app.adapters.masters_portal import DISCIPLINE_IDS, MastersPortalAdapter

from tests.test_masters_portal_discovery import _card

CARD_URL = "https://www.mastersportal.com/studies/123456/data-engineering.html"


def _wire(mocker, adapter, cards_by_call, scraped=False):
    mocker.patch.object(adapter, "discover_page", side_effect=cards_by_call)
    mocker.patch("app.adapters.masters_portal.polite_delay")
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 1, "scroll_offset": 0, "exhausted": False}
    state.is_url_scraped.return_value = scraped
    state.is_page_fetched.return_value = False
    return state


def test_card_document_carries_requirements_and_searchable_text():
    adapter = MastersPortalAdapter()
    doc = adapter._card_to_document(_card(), CARD_URL, "computer_science")
    record = doc["program_requirements"][0]

    assert record["country"] == "Germany"
    assert record["university"] == "TU Munich"
    assert record["program_name"] == "Data Engineering"
    assert record["min_ielts"] == 6.5
    assert record["discipline"] == "computer_science"
    assert record["deadline"] is None          # not on the card; Tier 2 supplies it
    assert record["content_hash"]

    # The document must be genuinely searchable, not a stub, and must carry provenance.
    assert "TU Munich" in doc["content"]
    assert CARD_URL in doc["content"]


def test_card_document_rejected_without_identity():
    """Same quality gate as the page path: no country means no row."""
    adapter = MastersPortalAdapter()
    assert adapter._card_to_document(_card(iso="US"), CARD_URL, "engineering") is None


@pytest.mark.asyncio
async def test_tier1_never_fetches_a_page(mocker):
    """The whole point: 20,000 programs without paying ~10s each."""
    adapter = MastersPortalAdapter()
    _wire(mocker, adapter, [([_card()], 1), ([], 1), ([], 1), ([], 1)])
    fetch = mocker.patch.object(adapter, "fetch_page")

    docs = await adapter.scrape_cards(per_run_cap_per_discipline=5)

    assert docs and all(d.get("program_requirements") for d in docs)
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_tier1_skips_out_of_scope_and_already_ingested(mocker):
    adapter = MastersPortalAdapter()
    _wire(mocker, adapter, [([_card(iso="US")], 1), ([], 1), ([], 1), ([], 1)])
    assert await adapter.scrape_cards(per_run_cap_per_discipline=5) == []

    adapter2 = MastersPortalAdapter()
    _wire(mocker, adapter2, [([_card()], 1), ([], 1), ([], 1), ([], 1)], scraped=True)
    assert await adapter2.scrape_cards(per_run_cap_per_discipline=5) == []


@pytest.mark.asyncio
async def test_tier1_respects_the_per_run_cap(mocker):
    adapter = MastersPortalAdapter()
    many = [_card(url=f"/studies/{i}/p.html") for i in range(20)]
    _wire(mocker, adapter, [(many, 100), (many, 100), (many, 100), (many, 100)])

    docs = await adapter.scrape_cards(per_run_cap_per_discipline=3)

    # Two disciplines are configured, so the cap applies per discipline.
    assert len(docs) <= 3 * len(DISCIPLINE_IDS)


@pytest.mark.asyncio
async def test_tier1_marks_extracted_not_scraped(mocker):
    """Same status contract as Tier 2: only the handler promotes to 'scraped' after a
    successful RAG upsert, so a failed upsert is retried rather than lost."""
    adapter = MastersPortalAdapter()
    state = _wire(mocker, adapter, [([_card()], 1), ([], 1), ([], 1), ([], 1)])

    await adapter.scrape_cards(per_run_cap_per_discipline=5)

    statuses = [c.args[3] for c in state.mark_url_status.call_args_list]
    assert "extracted" in statuses
    assert "scraped" not in statuses
    # Tier 1 does not fetch pages, so it must never claim the page axis.
    state.mark_page_status.assert_not_called()


@pytest.mark.asyncio
async def test_tier1_resumes_from_saved_offset(mocker):
    adapter = MastersPortalAdapter()
    seen = []

    async def fake_discover(discipline_id, offset):
        seen.append(offset)
        return [], 500

    mocker.patch.object(adapter, "discover_page", side_effect=fake_discover)
    mocker.patch("app.adapters.masters_portal.polite_delay")
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 6, "scroll_offset": 100, "exhausted": False}
    state.is_url_scraped.return_value = False

    await adapter.scrape_cards(per_run_cap_per_discipline=5)

    assert all(off == 100 for off in seen)

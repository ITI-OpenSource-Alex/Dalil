"""GOA-111 / Option B: the adapter must stamp the discipline it discovered under.

/match pre-filters on program_requirements.discipline (migration 022) — without it,
filtering can only use country, which at ~20,000 catalog programs still leaves
thousands of rows to score per request.
"""

import pytest

from app.adapters.masters_portal import DISCIPLINE_IDS, MastersPortalAdapter

from tests.test_masters_portal_discovery import PROGRAMME_HTML, _card

PROGRAM_URL = "https://www.mastersportal.com/studies/123456/data-engineering.html"


@pytest.mark.parametrize("discipline", sorted(DISCIPLINE_IDS))
def test_record_carries_the_discovering_discipline(discipline):
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(
        PROGRAMME_HTML, url=PROGRAM_URL, card=_card(), discipline=discipline
    )
    assert docs[0]["program_requirements"][0]["discipline"] == discipline


def test_discipline_is_null_when_unknown_not_guessed():
    """NULL keeps a program eligible in a filtered /match; a wrong guess would hide it
    from the users it actually suits."""
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(PROGRAMME_HTML, url=PROGRAM_URL, card=_card())
    assert docs[0]["program_requirements"][0]["discipline"] is None


@pytest.mark.asyncio
async def test_crawl_loop_passes_discipline_through(mocker):
    """The slug must survive the whole path: discovery bucket -> record."""
    adapter = MastersPortalAdapter()
    mocker.patch.object(adapter, "discover_page", side_effect=[([_card()], 1), ([], 1),
                                                              ([], 1), ([], 1)])
    mocker.patch.object(adapter, "fetch_page", return_value=PROGRAMME_HTML)
    mocker.patch("app.adapters.masters_portal.polite_delay")
    mocker.patch("app.adapters.masters_portal.robot_checker").is_allowed.return_value = True
    state = mocker.patch("app.adapters.masters_portal.crawl_state")
    state.get_cursor.return_value = {"last_page": 1, "scroll_offset": 0, "exhausted": False}
    state.is_url_scraped.return_value = False

    docs = await adapter.scrape(per_run_cap_per_discipline=2)

    disciplines = {r["discipline"] for d in docs for r in d.get("program_requirements", [])}
    assert disciplines and disciplines <= set(DISCIPLINE_IDS)

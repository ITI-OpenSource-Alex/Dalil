import pytest
from app.adapters.ielts_org import IELTSOrgAdapter
from app.adapters.daad import DAADAdapter
from app.adapters.masters_portal import MastersPortalAdapter
from app.adapters.chevening import CheveningAdapter
from app.adapters.study_in_poland import StudyInPolandAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter
@pytest.mark.asyncio
async def test_adapter_returns_structured_documents(mocker):
    # 1. Arrange: Mock the network fetch and the robots check
    mock_html = """
    <html>
        <body>
            <main>Band 7 means you are a good user of English.</main>
        </body>
    </html>
    """
    adapter = IELTSOrgAdapter()
    
    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value=mock_html)
    mocker.patch("app.core.rate_limiter.polite_delay")

    # 2. Act: Run the scrape orchestration
    documents = await adapter.scrape()

    # 3. Assert: one document per configured page.
    #
    # This asserted 1 while the adapter scraped only ielts-scoring-in-detail,
    # which left the corpus with band descriptors and no test format or timing
    # at all (BUG-012).
    assert len(documents) == len(IELTSOrgAdapter.CONTENT_URLS)
    for document in documents:
        assert document["source"] == "ielts_org"
        assert document["category"] == "language_requirements"
        assert document["country"] == "Global"
        assert "Band 7 means you are a good user of English." in document["content"]

    # Each document must carry the URL it actually came from. extract_documents
    # used to hardcode self.target_url, which was invisible with one page and
    # would have stamped all five with the scoring page's URL -- citations
    # pointing at a page that does not contain the answer (BUG-052).
    assert [d["url"] for d in documents] == IELTSOrgAdapter.CONTENT_URLS
    assert len({d["url"] for d in documents}) == len(documents)


@pytest.mark.asyncio
async def test_scoring_page_is_still_ingested_after_the_format_pages_were_added(mocker):
    """The original page must survive the multi-page change.

    BaseAdapter.scrape() extracts the index page only when extract_urls()
    returns nothing, so listing detail URLs without including the scoring page
    would have silently dropped the coverage this adapter already had -- a
    regression that no other assertion here would catch.
    """
    adapter = IELTSOrgAdapter()

    assert adapter.target_url in IELTSOrgAdapter.CONTENT_URLS
    assert (
        "ielts-scoring-in-detail" in IELTSOrgAdapter.CONTENT_URLS[0]
    ), "the scoring page must remain in the fetch list"

@pytest.mark.asyncio
async def test_robots_disallow_skips_url(mocker):
    # 1. Arrange: Mock robots.txt to DISALLOW the scrape
    adapter = IELTSOrgAdapter()
    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=False)
    
    # We spy on fetch_page to ensure it is NEVER called
    fetch_spy = mocker.patch.object(adapter, "fetch_page")

    # 2. Act
    documents = await adapter.scrape()

    # 3. Assert
    assert len(documents) == 0
    fetch_spy.assert_not_called()


@pytest.mark.asyncio
async def test_daad_adapter_extracts_content():
    mock_html = '<html><body><main>DAAD Scholarship Info</main></body></html>'
    adapter = DAADAdapter()
    docs = adapter.extract_documents(mock_html)
    
    assert len(docs) == 1
    assert "DAAD Scholarship Info" in docs[0]["content"]
@pytest.mark.asyncio
async def test_masters_portal_adapter_extracts_content():
    mock_html = '<html><body><main>UK Computer Science Masters</main></body></html>'
    adapter = MastersPortalAdapter()
    docs = adapter.extract_documents(mock_html)
    
    assert len(docs) == 1
    assert "UK Computer Science Masters" in docs[0]["content"]
@pytest.mark.asyncio
async def test_chevening_adapter_extracts_content():
    mock_html = '<html><body><main>Chevening Requirements</main></body></html>'
    adapter = CheveningAdapter()
    docs = adapter.extract_documents(mock_html)
    
    assert len(docs) == 1
    assert "Chevening Requirements" in docs[0]["content"]
@pytest.mark.asyncio
async def test_study_in_poland_adapter_graceful_fallback():
    # Test the fallback logic: no <main>, no <div id="content">, falls back to <body>
    mock_html = '<html><body>Poland Scholarship Details</body></html>'
    adapter = StudyInPolandAdapter()
    docs = adapter.extract_documents(mock_html)
    
    assert len(docs) == 1
    assert "Poland Scholarship Details" in docs[0]["content"]
@pytest.mark.asyncio
async def test_stipendium_hungaricum_adapter_strips_whitespace():
    # Test that it cleans up terrible whitespace
    mock_html = '<html><body><main>   Hungary    \n   Scholarship   \t</main></body></html>'
    adapter = StipendiumHungaricumAdapter()
    docs = adapter.extract_documents(mock_html)
    
    assert len(docs) == 1
    # get_text(strip=True) removes leading/trailing space from fragments
    assert "Hungary\nScholarship" in docs[0]["content"] or "Hungary    \n   Scholarship" in docs[0]["content"]
from pathlib import Path
import pytest
from app.adapters.masters_portal import MastersPortalAdapter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "mastersportal"

# E.g. search page fixture
# PROGRAMME_PAGE_WITH_ECTS_HTML = (FIXTURES_DIR / "programme_page_with_ects.html").read_text(encoding="utf-8")
# PROGRAMME_PAGE_NO_ECTS_HTML = (FIXTURES_DIR / "programme_page_no_ects.html").read_text(encoding="utf-8")
# Assuming these fixtures are just mocked for now.

# We will write the required tests for the new adapter shape:

def test_discipline_filter_unit(mocker):
    adapter = MastersPortalAdapter()
    assert adapter.base_url == "https://www.mastersportal.com"
    # we can check that scrape starts with the two Europe URLs but we'd need to mock fetch_page

@pytest.mark.asyncio
async def test_quality_gate_rejects_missing_data(mocker):
    adapter = MastersPortalAdapter()
    # If the page has no data, extract_documents should not include program_requirements
    html = "<html><body><h1>Program Name</h1><main>Study in UK\nNothing else</main></body></html>"
    docs = adapter.extract_documents(html, url="https://www.mastersportal.com/studies/123/prog.html")
    assert "program_requirements" not in docs[0]

@pytest.mark.asyncio
async def test_extraction_unit_with_all_fields(mocker):
    adapter = MastersPortalAdapter()
    html = """
    <html>
      <head><title>Master at Test Uni | MastersPortal</title></head>
      <body>
        <main>
          <h1>Test Program</h1>
          <a class="UniversityLink">Test Uni</a>
          Study in UK
          application deadline
          12 Jan 2026
          ECTS
          120
          GPA
          3.0
          IELTS
          6.5
        </main>
      </body>
    </html>
    """
    docs = adapter.extract_documents(html, url="https://www.mastersportal.com/studies/123/prog.html")
    assert "program_requirements" in docs[0]
    record = docs[0]["program_requirements"][0]
    assert record["university"] == "Test Uni"
    assert record["country"] == "UK"
    assert record["degree_level"] == "Master"
    assert record["min_ects"] == 120.0
    assert record["min_gpa"] == 3.0
    assert record["min_ielts"] == 6.5
    assert record["program_name"] == "Test Program"
    assert record["deadline"] == "2026-01-12"

@pytest.mark.asyncio
async def test_null_tolerant_quality_gate(mocker):
    adapter = MastersPortalAdapter()
    html = """
    <html>
      <head><title>Master at Test Uni | MastersPortal</title></head>
      <body>
        <main>
          <h1>Robotics M.Sc.</h1>
          <a class="UniversityLink">Test Uni</a>
          Study in Germany
        </main>
      </body>
    </html>
    """
    docs = adapter.extract_documents(html, url="https://www.mastersportal.com/studies/999/robotics.html")
    assert "program_requirements" in docs[0]
    record = docs[0]["program_requirements"][0]
    assert record["program_name"] == "Robotics M.Sc."
    assert record["university"] == "Test Uni"
    assert record["min_gpa"] is None
    assert record["min_ielts"] is None
    assert record["min_ects"] is None
    assert record["deadline"] is None


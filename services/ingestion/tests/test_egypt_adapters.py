import pytest

from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.aps_cairo import APSCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter

ARABIC_ONLY_HTML = (
    '<html lang="ar"><body><main>'
    'يجب على مقدم الطلب تقديم جواز سفر ساري المفعول وشهادة اجتياز اختبار '
    'اللغة الألمانية من أجل الحصول على تأشيرة الدراسة'
    '</main></body></html>'
)


# ---------------------------------------------------------------------------
# Task 07: GermanEmbassyCairoAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_german_embassy_cairo_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>National Visa Requirements</h2>
      <p>Applicants must provide a valid passport and an APS certificate.</p>
      <ul>
        <li>Valid passport</li>
        <li>APS certificate</li>
        <li>Proof of funds: EUR 11208 in a blocked account</li>
      </ul>
      <p>Processing time: 15-20 working days.</p>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html, url="https://kairo.diplo.de/visa")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Germany"
    assert doc["source"] == "german_embassy_cairo"
    assert "APS certificate" in doc["content"]

    visa_requirements = doc["visa_requirements"]
    assert len(visa_requirements) == 1
    record = visa_requirements[0]
    assert record["country"] == "Germany"
    assert record["issuing_body"] == "German Embassy Cairo"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 15
    assert record["processing_days_max"] == 20
    assert record["proof_of_funds"]["amount_eur"] == 11208.0
    assert "Valid passport" in record["requirements"]["items"]
    assert record["content_hash"]


@pytest.mark.asyncio
async def test_german_embassy_cairo_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>General Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>Completed application form</li>
      </ul>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None
    assert "Valid passport" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_german_embassy_cairo_skips_arabic_only_page():
    adapter = GermanEmbassyCairoAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


@pytest.mark.asyncio
async def test_german_embassy_cairo_multi_record_page_yields_multiple_entries():
    mock_html = """
    <html><body><main>
      <h2>Language Course Visa</h2>
      <ul>
        <li>Enrollment confirmation from language school</li>
        <li>Proof of funds: EUR 861 per month</li>
      </ul>
      <h2>Degree Study Visa</h2>
      <ul>
        <li>University admission letter</li>
        <li>APS certificate</li>
      </ul>
      <p>Processing time: 15-20 working days.</p>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    visa_requirements = docs[0]["visa_requirements"]
    assert len(visa_requirements) == 2
    visa_types = {r["visa_type"] for r in visa_requirements}
    assert any("Language Course Visa" in vt for vt in visa_types)
    assert any("Degree Study Visa" in vt for vt in visa_types)
    # Records must stay distinct on the (country, visa_type, issuing_body) key.
    assert len({r["visa_type"] for r in visa_requirements}) == 2


# ---------------------------------------------------------------------------
# Task 08: APSCairoAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aps_cairo_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>APS Certificate Procedure</h2>
      <p>The APS certificate verifies the authenticity of Egyptian academic credentials.</p>
      <ul>
        <li>Original university certificates</li>
        <li>Thanaweya Amma certificate</li>
      </ul>
      <p>Processing time: 20-30 working days.</p>
    </main></body></html>
    """
    adapter = APSCairoAdapter()
    docs = adapter.extract_documents(mock_html, url="https://www.aps-cairo.org/procedure")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Germany"
    assert doc["source"] == "aps_cairo"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "APS Cairo"
    assert record["country"] == "Germany"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 20
    assert record["processing_days_max"] == 30
    assert "Thanaweya Amma certificate" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_aps_cairo_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>APS Certificate Procedure</h2>
      <ul>
        <li>Original university certificates</li>
      </ul>
    </main></body></html>
    """
    adapter = APSCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_aps_cairo_skips_arabic_only_page():
    adapter = APSCairoAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


@pytest.mark.asyncio
async def test_aps_cairo_multiple_pathways_yield_multiple_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>University-track APS Certificate</h2>
      <ul>
        <li>Bachelor's degree certificate</li>
        <li>Foundation course (Studienkolleg) certificate if applicable</li>
      </ul>
      <p>Processing time: 10-15 working days.</p>
      <h2>Non-university-track APS Certificate</h2>
      <ul>
        <li>Thanaweya Amma certificate</li>
        <li>Proof of university admission</li>
      </ul>
      <p>Processing time: 20-25 working days.</p>
    </main></body></html>
    """
    adapter = APSCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    visa_requirements = docs[0]["visa_requirements"]
    assert len(visa_requirements) == 2

    by_heading = {r["notes"]: r for r in visa_requirements}
    assert by_heading["University-track APS Certificate"]["processing_days_min"] == 10
    assert by_heading["University-track APS Certificate"]["processing_days_max"] == 15
    assert by_heading["Non-university-track APS Certificate"]["processing_days_min"] == 20
    assert by_heading["Non-university-track APS Certificate"]["processing_days_max"] == 25


# ---------------------------------------------------------------------------
# Task 09: CampusFranceEgyptAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_campus_france_egypt_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>Études en France Procedure</h2>
      <p>Egyptian applicants must complete the Études en France procedure before applying
      for a long-stay student visa.</p>
      <ul>
        <li>Create a Campus France Egypt account</li>
        <li>Submit academic transcripts</li>
        <li>Attend an interview</li>
      </ul>
      <p>Processing time: 10-15 working days.</p>
    </main></body></html>
    """
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(mock_html, url="https://eg.campusfrance.org/procedure")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "France"
    assert doc["source"] == "campus_france_egypt"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "Campus France Egypt"
    assert record["country"] == "France"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 10
    assert record["processing_days_max"] == 15
    assert "Attend an interview" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_campus_france_egypt_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>Études en France Procedure</h2>
      <ul>
        <li>Create a Campus France Egypt account</li>
        <li>Submit academic transcripts</li>
      </ul>
    </main></body></html>
    """
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_campus_france_egypt_skips_arabic_only_page():
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []

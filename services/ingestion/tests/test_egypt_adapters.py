import pytest

from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter
from app.adapters.uk_visa_egypt import UKVISAEgyptAdapter
from app.adapters.fintiba_sperrkonto import FintibaSperrkontoAdapter
from app.adapters.czech_embassy_cairo import CzechEmbassyCairoAdapter
from app.adapters.spain_visa_egypt import SpainVisaEgyptAdapter
from app.adapters.italy_embassy_cairo import ItalyEmbassyCairoAdapter

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


def test_german_embassy_cairo_discovers_english_study_pdf_over_german_and_arabic():
    mock_html = """
    <html><body><main>
      <a href="/resource/blob/2573896/abc/250210-studium-deutsch-data.pdf">Merkblatt Studium (deutsch)</a>
      <a href="/resource/blob/2573898/def/250210-studium-englisch-data.pdf">Leaflet Study Visa for Germany</a>
      <a href="https://kairo.diplo.de/resource/blob/1624186/ghi/241120-merkblatt-studium-arab-data.pdf">Arabic leaflet</a>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    pdf_url = adapter._discover_study_pdf_url(mock_html)

    assert pdf_url == "https://kairo.diplo.de/resource/blob/2573898/def/250210-studium-englisch-data.pdf"


def test_german_embassy_cairo_falls_back_to_any_studium_pdf_if_no_english_variant():
    mock_html = """
    <html><body><main>
      <a href="/resource/blob/2573896/abc/250210-studium-deutsch-data.pdf">Merkblatt Studium (deutsch)</a>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    pdf_url = adapter._discover_study_pdf_url(mock_html)

    assert pdf_url == "https://kairo.diplo.de/resource/blob/2573896/abc/250210-studium-deutsch-data.pdf"


def test_german_embassy_cairo_no_pdf_link_yields_no_pdf_url():
    mock_html = "<html><body><main><a href='/other.pdf'>Unrelated</a></main></body></html>"
    adapter = GermanEmbassyCairoAdapter()

    assert adapter._discover_study_pdf_url(mock_html) is None


@pytest.mark.asyncio
async def test_german_embassy_cairo_scrape_appends_discovered_pdf_as_second_document(mocker):
    """Exercises the overridden scrape() end-to-end: landing page -> dynamic PDF
    discovery -> PDF download -> parse, mirroring StipendiumHungaricumAdapter's pattern."""
    landing_html = """
    <html><body><main>
      <h2>National Visa Requirements</h2>
      <ul><li>Valid passport</li></ul>
      <a href="/resource/blob/2573898/def/250210-studium-englisch-data.pdf">Leaflet Study Visa for Germany</a>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()

    mocker.patch("app.adapters.german_embassy_cairo.robot_checker.is_allowed", return_value=True)
    mocker.patch("app.adapters.german_embassy_cairo.polite_delay")
    mocker.patch.object(adapter, "fetch_page", return_value=landing_html)
    mocker.patch.object(adapter, "fetch_binary", return_value=b"%PDF-fake-bytes")

    fake_page = mocker.Mock()
    fake_page.extract_text.return_value = "Proof of funds: EUR 11208. Processing time: 15-20 working days."
    fake_reader = mocker.Mock()
    fake_reader.pages = [fake_page]
    mocker.patch("pypdf.PdfReader", return_value=fake_reader)

    docs = await adapter.scrape()

    assert len(docs) == 2
    landing_doc, pdf_doc = docs
    assert landing_doc["url"] == adapter.target_url
    assert pdf_doc["url"] == "https://kairo.diplo.de/resource/blob/2573898/def/250210-studium-englisch-data.pdf"
    assert "Proof of funds" in pdf_doc["content"]

    pdf_record = pdf_doc["visa_requirements"][0]
    assert pdf_record["processing_days_min"] == 15
    assert pdf_record["processing_days_max"] == 20
    assert pdf_record["proof_of_funds"]["amount_eur"] == 11208.0


@pytest.mark.asyncio
async def test_german_embassy_cairo_scrape_returns_landing_docs_only_when_pdf_missing(mocker):
    landing_html = """
    <html><body><main>
      <h2>National Visa Requirements</h2>
      <ul><li>Valid passport</li></ul>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()

    mocker.patch("app.adapters.german_embassy_cairo.robot_checker.is_allowed", return_value=True)
    mocker.patch("app.adapters.german_embassy_cairo.polite_delay")
    mocker.patch.object(adapter, "fetch_page", return_value=landing_html)
    fetch_binary_spy = mocker.patch.object(adapter, "fetch_binary")

    docs = await adapter.scrape()

    assert len(docs) == 1
    fetch_binary_spy.assert_not_called()


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


# ---------------------------------------------------------------------------
# Task 10: UKVISAEgyptAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_uk_visa_egypt_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>Student Route Visa Requirements</h2>
      <p>Applicants must demonstrate sufficient funds and provide a valid passport.</p>
      <ul>
        <li>Valid passport</li>
        <li>Confirmation of Acceptance for Studies (CAS)</li>
        <li>Proof of funds: EUR 1500</li>
      </ul>
      <p>Processing time: 15-20 working days.</p>
    </main></body></html>
    """
    adapter = UKVISAEgyptAdapter()
    docs = adapter.extract_documents(mock_html, url="https://www.gov.uk/student-visa")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "UK"
    assert doc["source"] == "uk_visa_egypt"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "UK Visas and Immigration (UKVI)"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 15
    assert record["processing_days_max"] == 20
    assert record["proof_of_funds"]["amount_eur"] == 1500.0
    assert "Valid passport" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_uk_visa_egypt_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>Student Route Visa Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>Confirmation of Acceptance for Studies (CAS)</li>
      </ul>
    </main></body></html>
    """
    adapter = UKVISAEgyptAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_uk_visa_egypt_skips_arabic_only_page():
    adapter = UKVISAEgyptAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


def test_uk_visa_egypt_extract_urls_discovers_child_guide_pages_only():
    mock_html = """
    <html><body>
      <a href="/student-visa/money">Money you need</a>
      <a href="/student-visa/knowledge-of-english">Knowledge of English</a>
      <a href="/student-visa/money">Money you need</a>
      <a href="/child-study-visa">Child Student visa</a>
      <a href="/browse/visas-immigration">Visas and immigration</a>
    </body></html>
    """
    adapter = UKVISAEgyptAdapter()
    urls = adapter.extract_urls(mock_html)

    assert urls == [
        "https://www.gov.uk/student-visa/money",
        "https://www.gov.uk/student-visa/knowledge-of-english",
    ]


# ---------------------------------------------------------------------------
# Task 12: FintibaSperrkontoAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fintiba_sperrkonto_happy_path_extracts_complete_proof_of_funds():
    mock_html = """
    <html><body><main>
      <h1>Blocked Account (Sperrkonto) for German Student Visa</h1>
      <p>The blocked account must contain EUR 11208 and be held for 12 months before
      your visa application.</p>
      <p>A sponsor letter is accepted as an alternative in some cases.</p>
      <p>Egyptian applicants should note that EGP transfers must be converted to EUR.</p>
      <ul>
        <li>Valid passport</li>
        <li>Blocked account confirmation</li>
      </ul>
    </main></body></html>
    """
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(mock_html, url="https://fintiba.com/sperrkonto")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Germany"
    assert doc["source"] == "fintiba_sperrkonto"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "Fintiba GmbH"
    assert record["egyptian_specific"] is True

    proof_of_funds = record["proof_of_funds"]
    assert proof_of_funds is not None
    assert proof_of_funds["amount_eur"] == 11208.0
    assert proof_of_funds["minimum_balance_period_days"] == 360
    assert proof_of_funds["accepted_account_types"] == ["blocked_account"]
    assert proof_of_funds["blocked_account_providers"] == ["Fintiba"]
    assert proof_of_funds["sponsor_letter_accepted"] is True
    assert proof_of_funds["notes_egypt"] is not None
    assert "egp" in proof_of_funds["notes_egypt"].lower() or "egypt" in proof_of_funds["notes_egypt"].lower()


@pytest.mark.asyncio
async def test_fintiba_sperrkonto_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h1>Blocked Account (Sperrkonto) for German Student Visa</h1>
      <p>The blocked account must contain EUR 11208.</p>
      <ul>
        <li>Valid passport</li>
      </ul>
    </main></body></html>
    """
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(mock_html)

    proof_of_funds = docs[0]["visa_requirements"][0]["proof_of_funds"]
    assert proof_of_funds["amount_eur"] == 11208.0
    assert proof_of_funds["minimum_balance_period_days"] is None
    assert proof_of_funds["sponsor_letter_accepted"] is None
    assert proof_of_funds["notes_egypt"] is None


@pytest.mark.asyncio
async def test_fintiba_sperrkonto_skips_arabic_only_page():
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


# ---------------------------------------------------------------------------
# Task 13: CzechEmbassyCairoAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_czech_embassy_cairo_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>Long-term Student Visa</h2>
      <p>Applicants must provide proof of accommodation and sufficient funds.</p>
      <ul>
        <li>Valid passport</li>
        <li>University acceptance letter</li>
        <li>Proof of funds: EUR 5000</li>
      </ul>
      <p>Processing time: 60-90 working days.</p>
    </main></body></html>
    """
    adapter = CzechEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html, url="https://www.mzv.cz/cairo/visa")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Czech Republic"
    assert doc["source"] == "czech_embassy_cairo"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "Embassy of the Czech Republic in Cairo"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 60
    assert record["processing_days_max"] == 90
    assert record["proof_of_funds"]["amount_eur"] == 5000.0
    assert "University acceptance letter" in record["requirements"]["items"]


@pytest.mark.asyncio
async def test_czech_embassy_cairo_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>Long-term Student Visa</h2>
      <ul>
        <li>Valid passport</li>
        <li>University acceptance letter</li>
      </ul>
    </main></body></html>
    """
    adapter = CzechEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_czech_embassy_cairo_skips_arabic_only_page():
    adapter = CzechEmbassyCairoAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


# ---------------------------------------------------------------------------
# Task 14: SpainVisaEgyptAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spain_visa_egypt_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <p>Applicants must provide proof of enrollment and sufficient financial means.</p>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
        <li>Proof of funds: EUR 6000</li>
      </ul>
      <p>Processing time: 30-45 working days.</p>
    </main></body></html>
    """
    adapter = SpainVisaEgyptAdapter()
    docs = adapter.extract_documents(mock_html, url="https://www.exteriores.gob.es/consulados/elcairo/visa")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Spain"
    assert doc["source"] == "spain_visa_egypt"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "Consulate General of Spain in Cairo"
    assert record["country"] == "Spain"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 30
    assert record["processing_days_max"] == 45
    assert record["proof_of_funds"]["amount_eur"] == 6000.0
    assert "University enrollment certificate" in record["requirements"]["items"]
    assert record["content_hash"]


@pytest.mark.asyncio
async def test_spain_visa_egypt_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
      </ul>
    </main></body></html>
    """
    adapter = SpainVisaEgyptAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_spain_visa_egypt_skips_arabic_only_page():
    adapter = SpainVisaEgyptAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


def test_spain_visa_egypt_extract_urls_discovers_study_visa_link():
    mock_html = """
    <html><body>
      <a href="/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Work-visas.aspx">Work visas</a>
      <a href="/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Student-visa.aspx">Student visa</a>
    </body></html>
    """
    adapter = SpainVisaEgyptAdapter()
    urls = adapter.extract_urls(mock_html)

    assert urls == [
        "https://exteriores.gob.es/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Student-visa.aspx"
    ]


def test_spain_visa_egypt_extract_urls_returns_empty_when_no_dedicated_page_exists():
    """When the consulate publishes no separate study-visa page, extract_urls must
    return [] so the base template falls back to scraping the landing page itself,
    rather than fabricating a link."""
    mock_html = """
    <html><body>
      <a href="/Embajadas/elcairo/en/ServiciosConsulares/Paginas/Consular/Work-visas.aspx">Work visas</a>
    </body></html>
    """
    adapter = SpainVisaEgyptAdapter()

    assert adapter.extract_urls(mock_html) == []


# ---------------------------------------------------------------------------
# Task 15: ItalyEmbassyCairoAdapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_italy_embassy_cairo_happy_path_extracts_documents_and_visa_requirements():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <p>Applicants must provide proof of enrollment and sufficient financial means.</p>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
        <li>Proof of funds: EUR 6000</li>
      </ul>
      <p>Processing time: 30-45 working days.</p>
    </main></body></html>
    """
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html, url="https://ambcairo.esteri.it/visa")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["country"] == "Italy"
    assert doc["source"] == "italy_embassy_cairo"

    record = doc["visa_requirements"][0]
    assert record["issuing_body"] == "Italian Embassy Cairo"
    assert record["country"] == "Italy"
    assert record["egyptian_specific"] is True
    assert record["processing_days_min"] == 30
    assert record["processing_days_max"] == 45
    assert record["proof_of_funds"]["amount_eur"] == 6000.0
    assert "University enrollment certificate" in record["requirements"]["items"]
    assert record["content_hash"]


@pytest.mark.asyncio
async def test_italy_embassy_cairo_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
      </ul>
    </main></body></html>
    """
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)

    record = docs[0]["visa_requirements"][0]
    assert record["processing_days_min"] is None
    assert record["processing_days_max"] is None
    assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_italy_embassy_cairo_skips_arabic_only_page():
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


# ---------------------------------------------------------------------------
# Definition of Done verification: specific extraction fields
# (fee, setup fee, step count, Declaration of Value, European number formats)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_german_embassy_cairo_parses_aps_requirement_and_european_amount_format():
    mock_html = """
    <html><body><main>
      <h2>National Visa Requirements</h2>
      <p>Applicants must provide a valid passport and an APS certificate from APS Cairo.</p>
      <ul>
        <li>Valid passport</li>
        <li>APS certificate</li>
        <li>Proof of funds: EUR 11.208,00 in a blocked account</li>
      </ul>
      <p>Processing time: 15-20 working days.</p>
    </main></body></html>
    """
    adapter = GermanEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert any("APS certificate" in item for item in record["requirements"]["items"])
    # European-format amount (period thousands separator, comma decimal) must parse
    # to the correct value, not be silently understated ~1000x.
    assert record["proof_of_funds"]["amount_eur"] == 11208.0


@pytest.mark.asyncio
async def test_campus_france_egypt_extracts_proof_of_funds_and_pre_registration_step_count():
    mock_html = """
    <html><body><main>
      <h2>Études en France Procedure</h2>
      <p>Applicants must show proof of funds of EUR 615 per month.</p>
      <ol>
        <li>Create a Campus France Egypt account</li>
        <li>Complete the online application</li>
        <li>Submit academic transcripts</li>
        <li>Attend an interview</li>
      </ol>
    </main></body></html>
    """
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert record["proof_of_funds"]["amount_eur"] == 615.0
    assert record["requirements"]["pre_registration_steps"] == 4


@pytest.mark.asyncio
async def test_fintiba_sperrkonto_extracts_setup_fee_and_egyptian_debit_acceptance():
    mock_html = """
    <html><body><main>
      <h1>Blocked Account (Sperrkonto) for German Student Visa</h1>
      <p>The blocked account must contain EUR 11208 and be held for 12 months.</p>
      <p>The setup fee is EUR 49.</p>
      <p>An Egyptian debit card is accepted for account setup and verification.</p>
      <ul>
        <li>Valid passport</li>
      </ul>
    </main></body></html>
    """
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    proof_of_funds = record["proof_of_funds"]
    assert proof_of_funds["setup_fee_eur"] == 49.0
    assert proof_of_funds["accepts_egyptian_debit"] is True


@pytest.mark.asyncio
async def test_fintiba_sperrkonto_egyptian_debit_not_accepted_is_detected():
    mock_html = """
    <html><body><main>
      <h1>Blocked Account (Sperrkonto) for German Student Visa</h1>
      <p>The blocked account must contain EUR 11208.</p>
      <p>An Egyptian debit card is not accepted for account setup.</p>
      <ul>
        <li>Valid passport</li>
      </ul>
    </main></body></html>
    """
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert record["proof_of_funds"]["accepts_egyptian_debit"] is False


@pytest.mark.asyncio
async def test_czech_embassy_cairo_extracts_document_checklist_and_processing_time():
    mock_html = """
    <html><body><main>
      <h2>Long-term Student Visa</h2>
      <ul>
        <li>Valid passport</li>
        <li>University acceptance letter</li>
        <li>Travel insurance</li>
      </ul>
      <p>Processing time: 60-90 working days.</p>
    </main></body></html>
    """
    adapter = CzechEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert record["requirements"]["items"] == [
        "Valid passport", "University acceptance letter", "Travel insurance"
    ]
    assert record["processing_days_min"] == 60
    assert record["processing_days_max"] == 90


@pytest.mark.asyncio
async def test_spain_visa_egypt_extracts_checklist_processing_time_and_proof_of_funds():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
        <li>Proof of financial means: EUR 600 per month</li>
      </ul>
      <p>Processing time: 30-45 working days.</p>
    </main></body></html>
    """
    adapter = SpainVisaEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert "Valid passport" in record["requirements"]["items"]
    assert "University enrollment certificate" in record["requirements"]["items"]
    assert record["processing_days_min"] == 30
    assert record["processing_days_max"] == 45
    assert record["proof_of_funds"]["amount_eur"] == 600.0


@pytest.mark.asyncio
async def test_italy_embassy_cairo_extracts_checklist_processing_time_and_proof_of_funds():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
        <li>Proof of financial means: EUR 448 per month</li>
      </ul>
      <p>Processing time: 30-45 working days.</p>
    </main></body></html>
    """
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert "Valid passport" in record["requirements"]["items"]
    assert record["processing_days_min"] == 30
    assert record["processing_days_max"] == 45
    assert record["proof_of_funds"]["amount_eur"] == 448.0


@pytest.mark.asyncio
async def test_italy_embassy_cairo_extracts_declaration_of_value_as_distinct_requirement():
    mock_html = """
    <html><body><main>
      <h2>National Visa (Type D) Requirements</h2>
      <ul>
        <li>Valid passport</li>
        <li>University enrollment certificate</li>
        <li>Declaration of Value for foreign academic qualifications</li>
      </ul>
      <p>Processing time: 30-45 working days.</p>
    </main></body></html>
    """
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    # Declaration of Value must be reported as its own distinct field...
    assert record["requirements"]["declaration_of_value"] == (
        "Declaration of Value for foreign academic qualifications"
    )
    # ...and not duplicated inside the general document checklist.
    assert "Declaration of Value for foreign academic qualifications" not in record["requirements"]["items"]
    assert "Valid passport" in record["requirements"]["items"]
    assert "University enrollment certificate" in record["requirements"]["items"]


# ---------------------------------------------------------------------------
# Regression tests: structured-extraction and target-page fixes identified by
# live inspection of the deployed adapters (post-GOA-086 hardening)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_campus_france_egypt_recovers_sections_wrapped_in_drupal_title_divs():
    """On the live site, each heading is wrapped in its own single-child title
    container, with the section body a sibling of that wrapper -- not of the
    heading itself. The direct-sibling walk finds nothing in that shape; the
    section must still be recovered via the wrapper's own siblings."""
    mock_html = """
    <html><body><main>
      <div class="layout-content">
        <div class="node__content">
          <div class="paragraph paragraph--type--rte">
            <div class="field field--name-field-title-paragraph"><h2>I create first my studies project</h2></div>
            <div class="clearfix text-formatted field field--name-field-descriptif">
              <p>Prepare your academic project and choose your institutions.</p>
            </div>
          </div>
          <div class="paragraph paragraph--type--rte">
            <div class="field field--name-field-title-paragraph"><h2>Then prepare your documents:</h2></div>
            <div class="clearfix text-formatted field field--name-field-descriptif">
              <ul><li>Passport</li><li>Diploma</li></ul>
            </div>
          </div>
        </div>
      </div>
    </main></body></html>
    """
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    records = docs[0]["visa_requirements"]

    notes = [r["notes"] for r in records]
    assert "I create first my studies project" in notes
    assert "Then prepare your documents:" in notes
    documents_record = next(r for r in records if r["notes"] == "Then prepare your documents:")
    assert documents_record["requirements"]["items"] == ["Passport", "Diploma"]


@pytest.mark.asyncio
async def test_campus_france_egypt_skips_sidebar_and_footer_widget_sections():
    """Related-article and footer-CTA widgets on this site are their own h2-headed
    sections but are not visa information -- they must not surface as bogus
    'requirements' records."""
    mock_html = """
    <html><body><main>
      <div class="node__content">
        <div class="paragraph paragraph--type--rte">
          <div class="field field--name-field-title-paragraph"><h2>Then prepare your documents:</h2></div>
          <div class="clearfix text-formatted field field--name-field-descriptif">
            <ul><li>Passport</li></ul>
          </div>
        </div>
        <div class="sur-le-meme-sujet">
          <h2>Sur le même sujet</h2>
          <div>Unrelated related-articles widget content.</div>
        </div>
        <div class="push-container">
          <h2>Follow the main steps to come study in France</h2>
          <a href="/steps">Some footer CTA link</a>
        </div>
      </div>
    </main></body></html>
    """
    adapter = CampusFranceEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    notes = [r["notes"] for r in docs[0]["visa_requirements"]]

    assert notes == ["Then prepare your documents:"]


@pytest.mark.asyncio
async def test_fintiba_sperrkonto_extracts_balance_period_when_duration_follows_amount():
    """The live page phrases the holding period as '<amount> for 12 months' rather
    than 'held/blocked/maintained for 12 months' -- both phrasings must resolve to
    a minimum_balance_period_days value instead of leaving it None."""
    mock_html = """
    <html><body><main>
      <h1>Blocked Account (Sperrkonto) for German Student Visa</h1>
      <p>The Blocked Account amount for Germany is EUR 11904 for 12 months.</p>
    </main></body></html>
    """
    adapter = FintibaSperrkontoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]

    assert record["proof_of_funds"]["amount_eur"] == 11904.0
    assert record["proof_of_funds"]["minimum_balance_period_days"] == 360


@pytest.mark.asyncio
async def test_uk_visa_egypt_extracts_processing_days_from_two_week_values():
    """gov.uk states decision times in weeks (e.g. one figure for applicants outside
    the UK, another for inside), not a 'N-M days' range -- both figures must be
    captured as processing_days_min/max rather than left None."""
    mock_html = """
    <html><body><main>
      <h2>How long it takes to get a decision</h2>
      <p>You'll usually get a decision on your visa within:</p>
      <ul>
        <li>3 weeks, if you're outside the UK</li>
        <li>8 weeks, if you're inside the UK</li>
      </ul>
      <h2>Money you need</h2>
      <p>You need enough money to support yourself during your course.</p>
    </main></body></html>
    """
    adapter = UKVISAEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    record = next(r for r in docs[0]["visa_requirements"] if r["notes"] == "How long it takes to get a decision")

    assert record["processing_days_min"] == 21
    assert record["processing_days_max"] == 56


@pytest.mark.asyncio
async def test_uk_visa_egypt_extracts_processing_days_from_single_week_value():
    mock_html = """
    <html><body><main>
      <h2>How long it takes to get a decision</h2>
      <p>You'll usually get a decision within 8 weeks.</p>
      <h2>Money you need</h2>
      <p>You need enough money to support yourself during your course.</p>
    </main></body></html>
    """
    adapter = UKVISAEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    record = next(r for r in docs[0]["visa_requirements"] if r["notes"] == "How long it takes to get a decision")

    assert record["processing_days_min"] == 56
    assert record["processing_days_max"] == 56


def test_uk_visa_egypt_extract_urls_dedupes_tracking_query_variants():
    """gov.uk emits both a plain link and a '?step-by-step-nav=<uuid>'-tagged variant
    of the same page -- these must not crawl as separate duplicate documents."""
    mock_html = """
    <html><body>
      <a href="/student-visa/money">Money you need</a>
      <a href="/student-visa/money?step-by-step-nav=abc123">Money you need</a>
      <a href="/student-visa/documents-you-must-provide">Documents you'll need</a>
    </body></html>
    """
    adapter = UKVISAEgyptAdapter()
    urls = adapter.extract_urls(mock_html)

    assert urls == [
        "https://www.gov.uk/student-visa/money",
        "https://www.gov.uk/student-visa/documents-you-must-provide",
    ]


@pytest.mark.asyncio
async def test_czech_embassy_cairo_extracts_processing_days_from_up_to_phrasing():
    """The live page states 'may take up to 60 days' -- a single upper bound, not an
    explicit 'N-M days' range -- so only processing_days_max should populate."""
    mock_html = """
    <html><body><main>
      <h2>Before you approach the Embassy:</h2>
      <p>The processing time for the study long-term visa may take up to 60 days.</p>
      <h2>Attachments</h2>
      <p>A list of required documents is attached below.</p>
    </main></body></html>
    """
    adapter = CzechEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = next(r for r in docs[0]["visa_requirements"] if r["notes"] == "Before you approach the Embassy:")

    assert record["processing_days_min"] is None
    assert record["processing_days_max"] == 60


@pytest.mark.asyncio
async def test_spain_visa_egypt_extracts_processing_days_from_spanish_month_phrasing():
    """This source only publishes in Spanish (e.g. 'en el plazo máximo de un mes') --
    the English 'N-M days' regex never matches, so a Spanish month/day fallback is
    required to avoid losing genuinely-present processing-time information."""
    mock_html = """
    <html><body><main>
      <h2>Procedimiento</h2>
      <p>La Oficina Consular resolverá el visado en el plazo máximo de un mes.</p>
      <h2>Documentos necesarios</h2>
      <ul><li>Pasaporte válido</li></ul>
    </main></body></html>
    """
    adapter = SpainVisaEgyptAdapter()
    docs = adapter.extract_documents(mock_html)
    record = next(r for r in docs[0]["visa_requirements"] if r["notes"] == "Procedimiento")

    assert record["processing_days_min"] is None
    assert record["processing_days_max"] == 30


@pytest.mark.asyncio
async def test_italy_embassy_cairo_recovers_checklist_from_plain_paragraphs():
    """This site authors its checklist as standalone <p> tags (not a <ul><li> list),
    and wraps the real article body alongside a sidebar nav widget under <main> --
    the sidebar's nav links must not be mistaken for checklist items, and the real
    paragraph-based checklist must be recovered instead of an empty items list."""
    mock_html = """
    <html><body><main>
      <div class="entry-content">
        <p>This is a long narrative introduction describing the visa in general terms
        at some length so that it clearly exceeds the two hundred character threshold
        used to tell prose paragraphs apart from short standalone checklist items.</p>
        <p>– Application form completed in English or Italian</p>
        <p>Valid passport with at least 18 months validity</p>
        <p>Declaration of Value if requested by University</p>
      </div>
      <aside class="widget-area">
        <h4>Naviga nella sezione</h4>
        <ul><li>Home&gt;</li><li>Study in Italy&gt;</li></ul>
      </aside>
    </main></body></html>
    """
    adapter = ItalyEmbassyCairoAdapter()
    docs = adapter.extract_documents(mock_html)
    record = docs[0]["visa_requirements"][0]
    items = record["requirements"]["items"]

    assert "Application form completed in English or Italian" in items
    assert "Valid passport with at least 18 months validity" in items
    assert record["requirements"]["declaration_of_value"] == "Declaration of Value if requested by University"
    assert not any("Home" in item or "Study in Italy" in item for item in items)
    assert not any(item.startswith("This is a long narrative") for item in items)

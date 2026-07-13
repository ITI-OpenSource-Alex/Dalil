import pytest

from app.adapters.german_embassy_cairo import GermanEmbassyCairoAdapter
from app.adapters.aps_cairo import APSCairoAdapter
from app.adapters.campus_france_egypt import CampusFranceEgyptAdapter
from app.adapters.uk_visa_egypt import UKVISAEgyptAdapter
from app.adapters.vfs_global_egypt import VFSGlobalEgyptAdapter
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


# ---------------------------------------------------------------------------
# Task 11: VFSGlobalEgyptAdapter
# ---------------------------------------------------------------------------

VFS_MULTI_COUNTRY_HTML = """
<html><body><main>
  <h2>Italy Visa Applications</h2>
  <ul>
    <li>Valid passport</li>
    <li>Appointment confirmation</li>
  </ul>
  <p>Processing time: 10-15 working days.</p>
  <h2>Czech Republic Visa Applications</h2>
  <ul>
    <li>Valid passport</li>
    <li>Travel insurance</li>
  </ul>
  <p>Processing time: 15-20 working days.</p>
</main></body></html>
"""


@pytest.mark.asyncio
async def test_vfs_global_egypt_multi_country_page_yields_one_record_per_country():
    adapter = VFSGlobalEgyptAdapter()
    docs = adapter.extract_documents(VFS_MULTI_COUNTRY_HTML, url="https://visa.vfsglobal.com/egy/en")

    assert len(docs) == 1
    doc = docs[0]
    assert doc["category"] == "visa"
    assert doc["source"] == "vfs_global_egypt"

    visa_requirements = doc["visa_requirements"]
    assert len(visa_requirements) == 2
    countries = {r["country"] for r in visa_requirements}
    assert countries == {"Italy", "Czech Republic"}
    for record in visa_requirements:
        assert record["issuing_body"] == "VFS Global Egypt"
        assert record["egyptian_specific"] is True


@pytest.mark.asyncio
async def test_vfs_global_egypt_partial_data_leaves_fields_none():
    mock_html = """
    <html><body><main>
      <h2>Spain Visa Applications</h2>
      <ul>
        <li>Valid passport</li>
      </ul>
      <h2>Netherlands Visa Applications</h2>
      <ul>
        <li>Valid passport</li>
        <li>Travel insurance</li>
      </ul>
    </main></body></html>
    """
    adapter = VFSGlobalEgyptAdapter()
    docs = adapter.extract_documents(mock_html)

    visa_requirements = docs[0]["visa_requirements"]
    assert len(visa_requirements) == 2
    for record in visa_requirements:
        assert record["processing_days_min"] is None
        assert record["processing_days_max"] is None
        assert record["proof_of_funds"] is None


@pytest.mark.asyncio
async def test_vfs_global_egypt_skips_arabic_only_page():
    adapter = VFSGlobalEgyptAdapter()
    docs = adapter.extract_documents(ARABIC_ONLY_HTML)

    assert docs == []


@pytest.mark.asyncio
async def test_vfs_global_egypt_no_known_country_yields_no_records():
    mock_html = """
    <html><body><main>
      <h2>General Information</h2>
      <ul>
        <li>Bring a valid passport</li>
      </ul>
    </main></body></html>
    """
    adapter = VFSGlobalEgyptAdapter()
    docs = adapter.extract_documents(mock_html)

    # No known destination country is genuinely named in the fixture, so nothing
    # should be fabricated.
    assert docs == []


@pytest.mark.asyncio
async def test_vfs_global_egypt_scrape_with_mocked_playwright_fetch(mocker):
    """Exercises the async Playwright-backed scrape() template method (fetch_page mocked,
    matching the existing adapter test pattern) rather than only extract_documents()."""
    adapter = VFSGlobalEgyptAdapter()
    mocker.patch("app.core.robots.robot_checker.is_allowed", return_value=True)
    mocker.patch.object(adapter, "fetch_page", return_value=VFS_MULTI_COUNTRY_HTML)
    mock_delay = mocker.patch("app.adapters.base_playwright_adapter.polite_delay")

    docs = await adapter.scrape()

    assert len(docs) == 1
    countries = {r["country"] for r in docs[0]["visa_requirements"]}
    assert countries == {"Italy", "Czech Republic"}
    mock_delay.assert_called_once_with(2.0, 3.0)


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

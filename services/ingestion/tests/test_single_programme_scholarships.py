"""BUG-010b regression: Chevening and Stipendium Hungaricum emit structured records.

Both adapters produced document chunks only, so scholarship_programs stayed empty
even on a fully successful run -- and GOA-024's matcher had nothing to match
against. Unlike DAAD these target a single named programme rather than a
catalogue, so each yields exactly one record.

The fixtures below are trimmed from the real live pages (captured 2026-07-26).
The assertions that matter most are the negative ones: this codebase's recurring
failure is extraction that looks plausible and is wrong, so the fields the pages
do not actually state must come back None rather than guessed.
"""
from app.adapters.chevening import CheveningAdapter
from app.adapters.stipendium_hungaricum import StipendiumHungaricumAdapter

# Trimmed from the live page. The "In this section" navigation block is retained
# deliberately -- it is what makes the generic "Who can apply?" section scan
# dangerous here (see test_eligibility_is_empty_not_navigation_chrome).
CHEVENING_HTML = """
<html><body><main>
<h1>Who can apply for a Chevening Scholarship?</h1>
<p>Chevening Scholarships allow exceptional individuals to study for a one-year
master&rsquo;s degree at a UK university.</p>
<div class="in-this-section">
  <span>In this section</span>
  <a href="/why-uk">Why study in the UK?</a>
  <a href="/who-can-apply">Who can apply?</a>
  <a href="/timeline">Application timeline</a>
  <a href="/course">Find a course</a>
  <a href="/faqs">FAQs</a>
</div>
<p>Applications for Chevening Scholarships are now closed.</p>
</main></body></html>
"""

# The landing page is a signpost; the substance is in the linked PDF.
STIPENDIUM_LANDING_HTML = """
<html><body><main>
<h2>CALL FOR APPLICATIONS - BA/BSC, MA/MSC</h2>
<p>You can find here the new call for applications and related information for
bachelor&rsquo;s, master&rsquo;s, one-tier master&rsquo;s and non-degree programmes 2026/2027.</p>
</main></body></html>
"""

# Text as pypdf extracts it from the real Call for Applications.
STIPENDIUM_PDF_TEXT = """
Call for Applications
for bachelor's, master's, one-tier master's, non-degree
programmes, and postgraduate specialist training courses
2026/2027

1. The Stipendium Hungaricum Scholarship Programme
1.3. Provisions Covered by the Scholarship
2. Eligibility
3.1. Application Timeline
"""


# ---------------------------------------------------------------------------
# Chevening
# ---------------------------------------------------------------------------

def test_chevening_emits_one_record_with_stable_identity():
    docs = CheveningAdapter().extract_documents(
        CHEVENING_HTML, url="https://www.chevening.org/scholarships/who-can-apply/"
    )

    records = docs[0]["scholarship_programs"]
    assert len(records) == 1
    record = records[0]

    # (provider, name) is the upsert key -- both must be present and stable, or
    # every run inserts a new row instead of updating one.
    assert record["provider"] == "Chevening"
    assert record["name"] == "Chevening Scholarship"
    assert record["country"] == "UK"
    assert record["content_hash"]


def test_chevening_reads_degree_level_from_the_page():
    docs = CheveningAdapter().extract_documents(CHEVENING_HTML)
    record = docs[0]["scholarship_programs"][0]

    assert record["degree_level"] == "Master"


def test_chevening_eligibility_is_empty_not_navigation_chrome():
    """The page carries a "Who can apply?" link inside its "In this section"
    navigation. DAAD's generic section scan would collect the sibling nav links
    ("Application timeline", "Find a course", "FAQs") as eligibility criteria --
    plausible-looking rows that are pure chrome. Empty is the honest answer."""
    docs = CheveningAdapter().extract_documents(CHEVENING_HTML)
    record = docs[0]["scholarship_programs"][0]

    assert record["eligibility"] == {}


def test_chevening_does_not_invent_a_deadline_or_award():
    """The live page states the deadline as prose with no date ("Applications ...
    are now closed") and links the award value to a separate page."""
    docs = CheveningAdapter().extract_documents(CHEVENING_HTML)
    record = docs[0]["scholarship_programs"][0]

    assert record["deadline"] is None
    assert record["award_amount"] is None


def test_chevening_still_produces_its_document_chunk():
    """Regression: the structured record is additive -- the vector corpus content
    this adapter already supplied must be unaffected."""
    docs = CheveningAdapter().extract_documents(CHEVENING_HTML)

    assert len(docs) == 1
    assert "Chevening Scholarships allow exceptional individuals" in docs[0]["content"]
    assert docs[0]["source"] == "chevening"
    assert docs[0]["category"] == "scholarships"


# ---------------------------------------------------------------------------
# Stipendium Hungaricum
# ---------------------------------------------------------------------------

def test_stipendium_landing_page_carries_the_key_but_no_record():
    """The record is built from the PDF in scrape(); the landing page keeps the
    key present so handler.py's pop() shape is uniform across adapters."""
    docs = StipendiumHungaricumAdapter().extract_documents(STIPENDIUM_LANDING_HTML)

    assert docs[0]["scholarship_programs"] == []


def test_stipendium_pdf_yields_one_record_with_stable_identity():
    adapter = StipendiumHungaricumAdapter()
    record = adapter._extract_scholarship(STIPENDIUM_PDF_TEXT, "https://example/call.pdf")

    assert record["provider"] == "Tempus Public Foundation"
    assert record["name"] == "Stipendium Hungaricum Scholarship Programme"
    assert record["country"] == "Hungary"
    assert record["content_hash"]


def test_stipendium_degree_level_is_none_because_one_call_spans_levels():
    """The call covers bachelor's, master's and one-tier master's study at once.
    Earliest-occurrence scanning would stamp the whole programme "Bachelor",
    which is not a truth about it."""
    adapter = StipendiumHungaricumAdapter()
    record = adapter._extract_scholarship(STIPENDIUM_PDF_TEXT, "https://example/call.pdf")

    assert record["degree_level"] is None


def test_stipendium_does_not_fabricate_ielts_gpa_amount_or_deadline():
    adapter = StipendiumHungaricumAdapter()
    record = adapter._extract_scholarship(STIPENDIUM_PDF_TEXT, "https://example/call.pdf")

    assert record["min_ielts"] is None
    assert record["min_gpa"] is None
    assert record["award_amount"] is None
    assert record["deadline"] is None


def test_stipendium_empty_text_yields_no_record():
    adapter = StipendiumHungaricumAdapter()

    assert adapter._extract_scholarship("   ", "https://example/call.pdf") is None

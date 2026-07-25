import pytest
import asyncpg
import json
import uuid
from app.core.config import settings
from app.schemas.scoring import UserProfile, ProgramRequirements
from app.services.gap_report import generate_gap_report
from app.services.visa_finance import clear_visa_finance_cache, get_student_visa_finance

def test_existing_gaps_typed_actionable():
    profile = UserProfile(userId="test_user", gpaScale="4.0", ieltsScore=5.5, gpa=3.0, workExperienceYears=1)
    program = ProgramRequirements(id="prog_1", min_ielts=6.5, min_gpa=3.5, min_work_experience=3)
    
    gaps = generate_gap_report(profile, program)
    
    assert gaps["ielts"]["type"] == "actionable"
    assert "IELTS 5.5 is below required 6.5" in gaps["ielts"]["message"]
    
    assert gaps["gpa"]["type"] == "actionable"
    assert "GPA 3.0 is below required 3.5" in gaps["gpa"]["message"]
    
    assert gaps["work_experience"]["type"] == "actionable"
    assert "Requires 3 years of experience" in gaps["work_experience"]["message"]

@pytest.mark.asyncio
async def test_financial_items_source_linked():
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestUK'")
        
        pof1 = json.dumps({"pathways": [{"pathway": "self_funded", "amounts": [{"amount": 1334, "currency": "GBP", "period": "per_month", "qualifier": "London"}]}]})
        # Both rows need a real figure: an amount-less pathway is now skipped as
        # unactionable. The assertion here is about independent attribution of two
        # sources (GOA-108), which still holds.
        pof2 = json.dumps({"pathways": [{"pathway": "scholarship", "amounts": [
            {"amount": 500, "currency": "GBP", "period": "per_month"}]}]})
        
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES 
            ($1, 'TestUK', 'Student Visa', 'Embassy 1', $2::jsonb, 'https://gov.uk/1', '{}'::jsonb),
            ($3, 'TestUK', 'Student Visa', 'Embassy 2', $4::jsonb, 'https://gov.uk/2', '{}'::jsonb)
        """, uuid.uuid4(), pof1, uuid.uuid4(), pof2)
        
        # Test directly with conn
        items = await get_student_visa_finance("TestUK", conn=conn)
        assert len(items) == 2
        assert items[0]["type"] == "informational"
        assert items[1]["type"] == "informational"
        assert items[0]["source_url"] == "https://gov.uk/1"
        assert items[1]["source_url"] == "https://gov.uk/2"
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestUK'")
        await conn.close()

@pytest.mark.asyncio
async def test_no_visa_data_omits_financial_key():
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'NonExistentCountry'")
        items = await get_student_visa_finance("NonExistentCountry", conn=conn)
        assert len(items) == 0
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_financial_never_actionable():
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestUK2'")
        pof = json.dumps({"pathways": [{"pathway": "self_funded", "amounts": []}]})
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES ($1, 'TestUK2', 'Student Visa', 'Embassy', $2::jsonb, 'http', '{}'::jsonb)
        """, uuid.uuid4(), pof)
        
        items = await get_student_visa_finance("TestUK2", conn=conn)
        for item in items:
            assert item["type"] == "informational"
            assert item["type"] != "actionable"
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestUK2'")
        await conn.close()

@pytest.mark.asyncio
async def test_per_country_finance_caching():
    """Calling get_student_visa_finance repeatedly for the same country memoizes in _VISA_FINANCE_CACHE."""
    from app.services.visa_finance import get_student_visa_finance, clear_visa_finance_cache, _VISA_FINANCE_CACHE
    
    clear_visa_finance_cache()
    
    conn = await asyncpg.connect(settings.database_url)
    try:
        assert "Germany" not in _VISA_FINANCE_CACHE
        res1 = await get_student_visa_finance("Germany", conn=conn)
        assert "Germany" in _VISA_FINANCE_CACHE
        assert _VISA_FINANCE_CACHE["Germany"] is res1
        
        # Subsequent calls return identical cached object
        res2 = await get_student_visa_finance("Germany", conn=conn)
        assert res2 is res1
    finally:
        clear_visa_finance_cache()
        await conn.close()


@pytest.mark.asyncio
async def test_pathway_without_amounts_or_evidence_is_not_rendered():
    """Proof-of-funds is what Egyptian applicants plan months ahead for. A pathway with
    no published figure produced items reading "requires proof of financial proof via
    self_funded", which tells a student nothing — observed live from
    gov.uk/student-visa (the landing page) before the source was repointed at
    gov.uk/student-visa/money, where the GBP figures are actually published."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestEmpty'")
        empty = json.dumps({"pathways": [{"pathway": "self_funded", "amounts": [],
                                          "notes": "the amount will vary"}]})
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES ($1, 'TestEmpty', 'Student Visa', 'Landing Page', $2::jsonb, 'https://gov.uk/x', '{}'::jsonb)
        """, uuid.uuid4(), empty)
        clear_visa_finance_cache()
        assert await get_student_visa_finance("TestEmpty", conn=conn) == []
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestEmpty'")
        clear_visa_finance_cache()
        await conn.close()


@pytest.mark.asyncio
async def test_pathway_with_evidence_but_no_amount_is_still_rendered():
    """Accepted evidence without a figure is still actionable ("bring a blocking
    confirmation"), so it must not be dropped along with the contentless case."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestEvid'")
        pof = json.dumps({"pathways": [{"pathway": "blocked_account", "amounts": [],
                                        "accepted_evidence": ["blocking confirmation"]}]})
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES ($1, 'TestEvid', 'Student Visa', 'Provider', $2::jsonb, 'https://x/1', '{}'::jsonb)
        """, uuid.uuid4(), pof)
        clear_visa_finance_cache()
        items = await get_student_visa_finance("TestEvid", conn=conn)
        assert len(items) == 1
        assert "blocked_account" in items[0]["message"]
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestEvid'")
        clear_visa_finance_cache()
        await conn.close()


@pytest.mark.asyncio
async def test_amounts_render_with_currency_and_qualifier():
    """The London / outside-London GBP distinction must survive into the message: it is
    a GBP 358/month difference in what the applicant must show."""
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestQual'")
        pof = json.dumps({"pathways": [{"pathway": "self_funded", "amounts": [
            {"amount": 1529, "currency": "GBP", "period": "per_month", "qualifier": "in London"},
            {"amount": 1171, "currency": "GBP", "period": "per_month", "qualifier": "outside London"}]}]})
        await conn.execute("""
            INSERT INTO visa_requirements (id, country, visa_type, issuing_body, proof_of_funds, source_url, requirements)
            VALUES ($1, 'TestQual', 'Student Visa', 'UKVI', $2::jsonb, 'https://gov.uk/money', '{}'::jsonb)
        """, uuid.uuid4(), pof)
        clear_visa_finance_cache()
        msg = (await get_student_visa_finance("TestQual", conn=conn))[0]["message"]
        assert "1529" in msg and "1171" in msg
        assert "GBP" in msg and "EUR" not in msg
        assert "London" in msg
    finally:
        await conn.execute("DELETE FROM visa_requirements WHERE country = 'TestQual'")
        clear_visa_finance_cache()
        await conn.close()

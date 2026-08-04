"""GOA-045 -- the FAQ volatility classifier.

Pure functions, no database, no network. The interesting cases are the
NEGATIVES: a classifier that blocks everything would pass a positives-only
suite while silently disabling the entire FAQ feature.
"""

import pytest

from app.services.faq_policy import classify_question, is_source_sensitive

# Questions that MUST reach live retrieval, with the volatility class expected.
# These are the ones where a cached answer is confidently wrong rather than
# merely stale.
VOLATILE_CASES = [
    # Amounts
    ("How much money do I need in my Sperrkonto?", "amount"),
    ("How much is the German student visa fee in Egypt?", "amount"),
    ("What is the cost of the APS certificate?", "amount"),
    ("Is the blocked account still 11208 EUR?", "amount"),
    ("Do I need €11,904 for the visa?", "amount"),
    # Proof of funds
    ("What is the proof of funds requirement for Germany?", "proof_of_funds"),
    ("What is the blocked account minimum for 2026?", "proof_of_funds"),
    ("Can my parents sponsor me instead of a blocked account?", "proof_of_funds"),
    # Deadlines
    ("What is the application deadline for the winter semester?", "deadline"),
    ("What is the last date to apply for a German student visa?", "deadline"),
    ("When is the application window for TU Munich?", "deadline"),
    # Eligibility
    ("Am I eligible for a German student visa with a 2.8 GPA?", "eligibility"),
    ("Do I qualify for a student visa with conditional admission?", "eligibility"),
    ("What is the minimum IELTS score for a German master's?", "eligibility"),
    ("Is there a maximum age for a German student visa?", "eligibility"),
    ("Is my IELTS 5.5 enough for a German student visa?", "eligibility"),
    # Processing times
    ("How long does the APS certificate take?", "processing_time"),
    ("What is the current visa processing time in Cairo?", "processing_time"),
]

# Questions that MUST stay eligible for the FAQ. Every one of these is a stable
# procedural explanation -- the answer is a process, not a number, and it does
# not change when an authority publishes a new fee schedule.
STABLE_CASES = [
    "How do I register for IELTS?",
    "How do I register for the IELTS exam in Egypt?",
    "What is a Studienkolleg?",
    "What is the Feststellungsprufung?",
    "How do I book a visa appointment through VFS Global Egypt?",
    "What documents are required for a German student visa application?",
    "Is health insurance required for the student visa application?",
    "Do I need to translate my documents into German?",
    "How do I authenticate my documents at the German embassy in Cairo?",
    "What is an APS certificate?",
    "Does the APS certificate expire?",
    "What happens if my visa gets rejected?",
    "Can my spouse accompany me on a student visa?",
    "What is a motivation letter?",
    "How do I open a blocked account?",
    "What is uni-assist and how does it work?",
]


@pytest.mark.parametrize("question,expected_reason", VOLATILE_CASES)
def test_source_sensitive_questions_bypass_the_faq(question, expected_reason):
    result = classify_question(question)
    assert not result.allowed, (
        f"{question!r} would have been served from static text; its answer "
        "depends on a figure an authority can change"
    )
    assert result.reason == expected_reason, (
        f"{question!r} classified as {result.reason!r}, expected {expected_reason!r} "
        "-- the label drives the bypass metric, so a wrong one hides which class "
        "of volatility is actually being hit"
    )
    assert is_source_sensitive(question) is True


@pytest.mark.parametrize("question", STABLE_CASES)
def test_stable_procedural_questions_stay_eligible(question):
    result = classify_question(question)
    assert result.allowed, (
        f"{question!r} was blocked as source-sensitive. This is the failure mode "
        "that silently disables the FAQ: it costs a token spend on every query "
        "while every test about volatile questions still passes"
    )
    assert result.reason is None
    assert is_source_sensitive(question) is False


def test_open_a_blocked_account_is_procedure_but_its_minimum_is_not():
    """The pair that motivates the whole module.

    These two questions are lexically close enough for pg_trgm to confuse them,
    and have completely different answers: one is a procedure that has not
    changed in years, the other is a number revised annually. Curation alone
    cannot separate them -- only classifying the question can.
    """
    assert classify_question("How do I open a blocked account?").allowed
    assert not classify_question(
        "How much do I need in a blocked account?"
    ).allowed


def test_empty_and_whitespace_questions_are_not_treated_as_volatile():
    # An empty question is a caller bug, not a volatile question. It should fall
    # through to normal handling rather than being silently routed anywhere.
    for question in ("", "   ", "\n"):
        assert classify_question(question).allowed
        assert classify_question(question).reason is None


def test_classification_is_case_insensitive():
    for variant in (
        "HOW MUCH MONEY DO I NEED IN MY SPERRKONTO?",
        "how much money do i need in my sperrkonto?",
        "How Much Money Do I Need In My Sperrkonto?",
    ):
        assert not classify_question(variant).allowed

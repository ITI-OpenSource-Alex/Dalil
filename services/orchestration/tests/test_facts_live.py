"""GOA-038 -- what the real model does with stored facts.

The mocked tests in test_facts_context.py prove the plumbing: facts reach the
prompt, the prompt reaches the classifier, the rewrite reaches RAG. None of them
can prove the link in the middle -- that the model actually uses a stored fact
to resolve an under-specified question, and, more importantly, that it does NOT
staple the user's profile onto a question that never asked for it.

That risk is the whole reason Option A was a decision rather than an obvious
choice (plan section 3.1), so it is pinned here against the real gateway and
replayed from cassettes in CI.

Cost model matches test_agentrouter.py:
- `pytest` replays the committed cassettes. Zero network, zero cost.
- `RUN_LIVE_LLM_TESTS=1 pytest tests/test_facts_live.py` re-records.

Re-record after changing SUPERVISOR_PROMPT or USER_FACTS_INJECTION -- the
cassettes hold the old prompt.
"""

import os

import pytest

from app.schemas.facts import StoredFact
from app.services.supervisor import classify_intent

LIVE = os.getenv("RUN_LIVE_LLM_TESTS") == "1"

_PLACEHOLDER_KEYS = (None, "", "not-configured", "dummy-key")
_has_token = (
    os.getenv("ANTHROPIC_AUTH_TOKEN") not in _PLACEHOLDER_KEYS
    or os.getenv("ANTHROPIC_API_KEY") not in _PLACEHOLDER_KEYS
)

live_requires_token = pytest.mark.skipif(
    LIVE and not _has_token,
    reason="RUN_LIVE_LLM_TESTS=1 requires a valid ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY",
)


def profile() -> list[StoredFact]:
    return [
        StoredFact(
            fact_type="degree",
            fact_key="",
            fact_value="BSc in Electrical and Electronic Engineering",
            confidence=0.9,
            revision=1,
        ),
        StoredFact(
            fact_type="gpa", fact_key="", fact_value="3.2", confidence=0.9, revision=1
        ),
        StoredFact(
            fact_type="target_country",
            fact_key="",
            fact_value="Germany",
            confidence=0.9,
            revision=1,
        ),
    ]


@pytest.mark.vcr
@live_requires_token
@pytest.mark.asyncio
async def test_u28_an_implicit_question_is_resolved_from_stored_facts():
    """"my GPA" has no referent in this session. It has one in the user's profile."""
    result = await classify_intent("Is my GPA good enough?", user_facts=profile())

    assert "3.2" in result.standalone_question, (
        f"stored GPA did not reach the rewritten question: {result.standalone_question!r}"
    )


@pytest.mark.vcr
@live_requires_token
@pytest.mark.asyncio
async def test_u27_facts_do_not_leak_into_an_unrelated_question():
    """The failure mode Option A was chosen despite.

    A general question must stay general. Stapling the user's degree, GPA and
    target country onto "what are the visa requirements?" changes the question,
    and RAG would then answer the changed one -- retrieving against a query the
    user never asked, and citing sources for it.
    """
    result = await classify_intent(
        "What are the visa requirements?", user_facts=profile()
    )

    rewritten = result.standalone_question or ""
    for leaked in ("3.2", "Electrical", "Electronic Engineering"):
        assert leaked not in rewritten, (
            f"{leaked!r} was added to a question that did not ask for it: {rewritten!r}"
        )


@pytest.mark.vcr
@live_requires_token
@pytest.mark.asyncio
async def test_routing_is_unaffected_by_the_presence_of_facts():
    """Facts are for resolving references, not for deciding where a message goes."""
    result = await classify_intent("I want to practice speaking", user_facts=profile())

    assert result.intent == "SPEAKING"

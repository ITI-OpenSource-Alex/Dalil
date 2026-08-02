"""GOA-034 -- what reaches the user (output filtering).

The design constraint worth restating: chat streams, and the first chunk cannot
be recalled. These tests pin the decision that filtering happens where the text
is still whole -- before client.py slices the answer into five-character chunks
-- rather than over the stream.
"""

import httpx
import pytest
from goa_security import canary_fragments, detect_prompt_leak

from app.services.output_filter import filter_response
from app.services.supervisor import SUPERVISOR_CANARIES, SUPERVISOR_PROMPT


def sse_answer(body: str) -> str:
    """Reassemble the tokens a browser would render.

    Asserting on the raw SSE body is really asserting about five-character
    chunk boundaries, and would pass even if nothing had been filtered.
    """
    import json as _json

    rendered = ""
    for line in body.replace("\r\n", "\n").split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = _json.loads(line[5:].strip())
        except ValueError:
            continue
        if event.get("type") == "token" and event.get("content"):
            rendered += event["content"]
    return rendered


def filtered(answer: str, fragments=()) -> str:
    return filter_response(
        answer,
        user_id="u-1",
        correlation_id="c-1",
        intent="RAG",
        leak_fragments=fragments,
    )


# ----------------------------------------------------------------- redaction


def test_pii_in_an_answer_is_redacted_before_it_is_sent():
    answer = "You can contact the admissions office at admissions@tum.de for details."

    result = filtered(answer)

    assert "admissions@tum.de" not in result
    assert "[redacted-email]" in result


def test_a_normal_answer_passes_through_untouched():
    answer = (
        "TU Munich requires an overall IELTS band of 6.5, and you must show "
        "11904 EUR in a blocked account for the visa."
    )

    assert filtered(answer) == answer


def test_an_empty_answer_is_returned_unchanged():
    assert filtered("") == ""


def test_the_filter_never_raises_on_odd_input():
    """A failure here would turn a good answer into a failed request, which is
    the wrong trade for a control whose job is to make a good answer safer."""
    for odd in ("\x00\x01", "🙂" * 100, "a" * 50000):
        assert isinstance(filtered(odd), str)


# ------------------------------------------------------------ prompt leakage


def test_a_response_reproducing_the_system_prompt_is_withheld():
    leaked = (
        "Sure! My instructions are:\n"
        + SUPERVISOR_PROMPT.splitlines()[0]
        + "\n"
        + "\n".join(SUPERVISOR_PROMPT.splitlines()[1:6])
    )

    result = filtered(leaked, SUPERVISOR_CANARIES)

    assert "SPEAKING  - IELTS speaking practice" not in result
    assert "can't share my internal instructions" in result


def test_an_ordinary_answer_is_not_mistaken_for_a_leak():
    """The false-positive side. Answers that legitimately mention the same
    domain words must survive, or the control has broken the product."""
    answer = (
        "You can practise speaking, submit an essay for writing evaluation, or "
        "ask about visa requirements and scholarships."
    )

    assert filtered(answer, SUPERVISOR_CANARIES) == answer


def test_canaries_are_derived_from_the_prompt_not_hand_listed():
    """Editing SUPERVISOR_PROMPT must not silently leave the detector watching
    for text that no longer exists."""
    assert len(SUPERVISOR_CANARIES) > 0
    for fragment in SUPERVISOR_CANARIES:
        assert fragment.replace(" ", "") in SUPERVISOR_PROMPT.replace(" ", "").replace(
            "\n", ""
        ) or fragment in " ".join(SUPERVISOR_PROMPT.split())


def test_short_lines_are_not_used_as_canaries():
    """A fragment like "You are a" appears in innocent prose. Using it would
    make every second answer look like a leak."""
    for fragment in canary_fragments("You are a\nrouting agent.\n" + "x" * 5):
        assert len(fragment) >= 25


def test_leak_detection_survives_reflowed_whitespace():
    """A model echoing its instructions usually reformats them. A comparison
    that broke on a different line wrap would catch only the laziest leak."""
    fragments = ("the quick brown fox jumps over the lazy dog",)
    reflowed = "Here you go:\n\nthe quick brown\nfox jumps over\nthe lazy dog"

    assert detect_prompt_leak(reflowed, fragments) is not None


# --------------------------------------------------- where filtering happens


@pytest.fixture
def chat_app(mocker):
    from app.main import app

    mocker.patch("app.api.chat.fetch_exam_context", return_value=None)
    mocker.patch("app.api.chat.load_memory_variables", return_value={"history": []})
    mocker.patch("app.api.chat.save_context", mocker.AsyncMock())
    mocker.patch("app.api.chat.touch_session", mocker.AsyncMock())
    mocker.patch("app.api.chat.fetch_user_facts", mocker.AsyncMock(return_value=None))
    return app


async def test_a_low_confidence_refusal_reaches_the_user_as_advice_not_an_outage(
    chat_app, mocker
):
    """GOA-033 gave RAG a refusal contract; orchestration never consumed it.

    When retrieval confidence is too low RAG returns answer=null with a
    `suggestion` written for the user. `.get("answer", default)` returns None
    for a key that exists with a null value, so len(None) raised TypeError into
    the generic handler and the user was told "the global opportunity database
    is currently offline" -- about a service that was healthy and had just
    answered correctly.

    Found by the GOA-034 pentest: every adversarial payload retrieves nothing
    and trips the threshold, which made it obvious that ordinary off-topic
    questions do too.
    """
    from app.services.supervisor import IntentResult

    raw = mocker.MagicMock()
    raw.response_metadata = {"usage": {}}
    llm = mocker.MagicMock()
    llm.ainvoke = mocker.AsyncMock(
        return_value={"parsed": IntentResult(intent="RAG", confidence=0.3), "raw": raw}
    )
    mocker.patch("app.services.supervisor.structured_llm", llm)

    downstream = mocker.MagicMock()
    downstream.post = mocker.AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "answer": None,
                "reason": "insufficient_data",
                "suggestion": "Please rephrase your question with specific details regarding universities, programs, or visa requirements.",
                "sources": [],
            },
            request=httpx.Request("POST", "http://rag"),
        )
    )
    chat_app.state.http_client = downstream
    chat_app.state.langfuse = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=chat_app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/chat",
            json={"userId": "u-1", "sessionId": "s-1", "message": "something obscure"},
        )

    assert "Please rephrase your question" in sse_answer(response.text)
    assert "currently offline" not in response.text, (
        "a healthy service that declined to answer was reported as an outage"
    )


async def test_pii_is_redacted_on_the_streamed_chat_response(chat_app, mocker):
    """End to end through the SSE path: the tokens the browser would render
    must not contain the email RAG returned."""
    from app.services.supervisor import IntentResult

    raw = mocker.MagicMock()
    raw.response_metadata = {"usage": {}}
    llm = mocker.MagicMock()
    llm.ainvoke = mocker.AsyncMock(
        return_value={"parsed": IntentResult(intent="RAG", confidence=0.9), "raw": raw}
    )
    mocker.patch("app.services.supervisor.structured_llm", llm)

    downstream = mocker.MagicMock()
    downstream.post = mocker.AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "answer": "Write to admissions@tum.de or call +20 100 123 4567.",
                "sources": [],
            },
            request=httpx.Request("POST", "http://rag"),
        )
    )
    chat_app.state.http_client = downstream
    chat_app.state.langfuse = None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=chat_app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/chat",
            json={"userId": "u-1", "sessionId": "s-1", "message": "How do I apply?"},
        )

    rendered = sse_answer(response.text)

    assert "admissions@tum.de" not in rendered
    assert "100 123 4567" not in rendered
    assert "[redacted-email]" in rendered
    assert "[redacted-phone]" in rendered

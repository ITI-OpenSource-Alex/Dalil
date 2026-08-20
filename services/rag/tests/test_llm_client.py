"""GOA-135 — cost accounting, client lifecycle and retry policy in the RAG service.

The defects these cover, all measured in perf/reports/GOA-135-pre-*.json:
  * cost priced at Haiku's $0.25/$1.25 against the then-current $2/$10 table
    -> 8x understated before the later AgentRouter pricing refresh
  * a fresh AsyncAnthropic per call, never closed              -> 20 TCP connects
    and p50 917.6ms where one reused client gives 1 and 296.7ms
  * `except Exception` retrying a permanent 401                -> 2 requests, 1.2s
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from app.services import rag_service


LIVE = os.getenv("RUN_LIVE_LLM_TESTS") == "1"


@pytest.fixture(autouse=True)
def _reset_client():
    rag_service._llm_client = None
    yield
    rag_service._llm_client = None


# --- pricing --------------------------------------------------------------

def test_cost_uses_configured_model_pricing():
    """2,000 prompt + 300 completion on claude-opus-4-8 is $0.021, not $0.0009."""
    from goa_pricing import cost_usd

    with patch.object(rag_service.settings, "llm_model", "claude-opus-4-8"):
        assert cost_usd(rag_service.settings.llm_model, 2000, 300) == pytest.approx(0.021)


def test_cost_is_not_the_old_haiku_arithmetic():
    """The exact regression. 0.25/1.25 on this shape gives $0.000875."""
    from goa_pricing import cost_usd

    old = (2000 * 0.25 + 300 * 1.25) / 1_000_000
    assert cost_usd("claude-opus-4-8", 2000, 300) != pytest.approx(old)


def test_unknown_model_reports_none_not_zero():
    from goa_pricing import cost_usd

    result = cost_usd("model-that-does-not-exist", 2000, 300)
    assert result is None
    assert result != 0.0


def test_pricing_table_covers_the_configured_model():
    """Fails the moment someone switches LLM_MODEL without pricing it — the
    failure mode that let this defect ship."""
    from goa_pricing import known_models

    assert rag_service.settings.llm_model in known_models(), (
        f"{rag_service.settings.llm_model} is not in the shared price table; "
        "add it to LLM_PRICING_JSON and to the Gateway's copy"
    )


# --- client lifecycle -----------------------------------------------------

def test_anthropic_client_is_module_singleton():
    first = rag_service.get_llm_client()
    second = rag_service.get_llm_client()
    assert first is second, "a new client per call is the 620ms-per-query defect"


def test_client_is_lazily_created_when_lifespan_did_not_run():
    assert rag_service._llm_client is None
    client = rag_service.get_llm_client()
    assert client is not None
    assert rag_service._llm_client is client


def test_init_llm_client_builds_the_singleton():
    asyncio.run(rag_service.init_llm_client())
    assert rag_service._llm_client is not None


def test_close_llm_client_closes_and_clears():
    fake = MagicMock()
    fake.close = AsyncMock()
    rag_service._llm_client = fake

    asyncio.run(rag_service.close_llm_client())

    fake.close.assert_awaited_once()
    assert rag_service._llm_client is None


def test_close_llm_client_is_safe_when_never_built():
    asyncio.run(rag_service.close_llm_client())  # must not raise


def test_close_clears_the_client_even_if_close_raises():
    """A shutdown that already went wrong must not also leak the client."""
    fake = MagicMock()
    fake.close = AsyncMock(side_effect=RuntimeError("boom"))
    rag_service._llm_client = fake

    with pytest.raises(RuntimeError):
        asyncio.run(rag_service.close_llm_client())

    assert rag_service._llm_client is None


def test_invoke_uses_the_shared_client():
    """_invoke_via_sdk must not construct its own — that was the defect."""
    block = MagicMock()
    block.text = "answer"
    response = MagicMock()
    response.content = [block]
    response.usage = MagicMock(input_tokens=10, output_tokens=5)

    shared = MagicMock()
    shared.messages.create = AsyncMock(return_value=response)
    rag_service._llm_client = shared

    with patch.object(rag_service, "AsyncAnthropic") as ctor:
        result = asyncio.run(rag_service._invoke_via_sdk("hello"))

    ctor.assert_not_called()
    shared.messages.create.assert_awaited_once()
    assert result.content == "answer"


def test_invoke_streams_provider_tokens_before_completion():
    usage = MagicMock(input_tokens=10, output_tokens=3)

    class FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        @property
        def text_stream(self):
            async def chunks():
                yield "First "
                yield "token"

            return chunks()

        async def get_final_message(self):
            return MagicMock(usage=usage)

    shared = MagicMock()
    shared.messages.stream = MagicMock(return_value=FakeStream())
    rag_service._llm_client = shared
    received = []

    async def collect(chunk):
        received.append(chunk)

    result = asyncio.run(rag_service._invoke_via_sdk("hello", collect))

    assert received == ["First ", "token"]
    assert result.content == "First token"
    assert result.response_metadata["usage"] is usage
    shared.messages.stream.assert_called_once()


@pytest.mark.skipif(not LIVE, reason="paid AgentRouter canary is opt-in")
@pytest.mark.asyncio
async def test_live_anthropic_stream_returns_incremental_text():
    """Canary the exact wire path used by `/query/stream`, not the OpenAI shim."""
    received = []

    async def collect(chunk):
        received.append(chunk)

    response = await rag_service._invoke_via_sdk(
        "Reply with exactly: OK",
        token_callback=collect,
    )

    assert received
    assert "".join(received) == response.content
    assert "OK" in response.content


# --- retry policy ---------------------------------------------------------

def _api_error(cls):
    """Build an anthropic API error without going through its __init__ contract."""
    return cls.__new__(cls)


@pytest.mark.parametrize(
    "exc",
    [
        _api_error(anthropic.APITimeoutError),
        _api_error(anthropic.APIConnectionError),
        _api_error(anthropic.InternalServerError),
        _api_error(anthropic.RateLimitError),
        httpx.ConnectTimeout("slow"),
        httpx.ReadError("reset"),
    ],
)
def test_retries_transient_failures(exc):
    calls = {"n": 0}

    async def flaky(_prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise exc
        return "ok"

    with patch.object(rag_service, "_invoke_via_sdk", side_effect=flaky), \
            patch.object(rag_service.asyncio, "sleep", new=AsyncMock()):
        result = asyncio.run(rag_service._invoke_llm_with_retry("p"))

    assert result == "ok"
    assert calls["n"] == 2


@pytest.mark.parametrize(
    "cls",
    [
        anthropic.AuthenticationError,   # 401 — measured at 2 requests pre-fix
        anthropic.BadRequestError,       # 400
        anthropic.NotFoundError,         # 404 — a deprecated model id (GOA-120 D4)
        anthropic.PermissionDeniedError, # 403
    ],
)
def test_does_not_retry_permanent_failures(cls):
    calls = {"n": 0}
    exc = _api_error(cls)

    async def always_fails(_prompt):
        calls["n"] += 1
        raise exc

    with patch.object(rag_service, "_invoke_via_sdk", side_effect=always_fails), \
            patch.object(rag_service.asyncio, "sleep", new=AsyncMock()):
        with pytest.raises(cls):
            asyncio.run(rag_service._invoke_llm_with_retry("p"))

    assert calls["n"] == 1, f"{cls.__name__} was retried; it can never succeed"


def test_retry_backs_off_between_attempts():
    async def always_times_out(_prompt):
        raise _api_error(anthropic.APITimeoutError)

    sleeper = AsyncMock()
    with patch.object(rag_service, "_invoke_via_sdk", side_effect=always_times_out), \
            patch.object(rag_service.asyncio, "sleep", new=sleeper):
        with pytest.raises(anthropic.APITimeoutError):
            asyncio.run(rag_service._invoke_llm_with_retry("p", attempts=2))

    sleeper.assert_awaited_once()
    assert sleeper.await_args.args[0] > 0


def test_no_sleep_after_the_final_attempt():
    """Backing off after the last try only delays the error the caller already has."""
    async def always_times_out(_prompt):
        raise _api_error(anthropic.APITimeoutError)

    sleeper = AsyncMock()
    with patch.object(rag_service, "_invoke_via_sdk", side_effect=always_times_out), \
            patch.object(rag_service.asyncio, "sleep", new=sleeper):
        with pytest.raises(anthropic.APITimeoutError):
            asyncio.run(rag_service._invoke_llm_with_retry("p", attempts=1))

    sleeper.assert_not_awaited()


def test_retry_counter_is_labelled_by_reason():
    from app.core.metrics import LLM_RETRIES_TOTAL

    before = LLM_RETRIES_TOTAL.labels(reason="APITimeoutError")._value.get()

    calls = {"n": 0}

    async def flaky(_prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _api_error(anthropic.APITimeoutError)
        return "ok"

    with patch.object(rag_service, "_invoke_via_sdk", side_effect=flaky), \
            patch.object(rag_service.asyncio, "sleep", new=AsyncMock()):
        asyncio.run(rag_service._invoke_llm_with_retry("p"))

    after = LLM_RETRIES_TOTAL.labels(reason="APITimeoutError")._value.get()
    assert after == before + 1


# --- dead code ------------------------------------------------------------

def test_chat_anthropic_is_gone_from_rag_service():
    """It was constructed at import, configured with care, and never called.

    Guards against a merge restoring it — the next person tuning RAG's LLM timeout
    would edit it and see no effect.

    Asserted against the parsed AST rather than the raw text: the comment that
    explains the deletion necessarily names the thing deleted, and a substring
    check on source cannot tell an explanation from a resurrection.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(rag_service.__file__).read_text(encoding="utf-8"))

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "langchain_anthropic"
        for alias in node.names
    }
    assert "ChatAnthropic" not in imported

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "ChatAnthropic" not in called
    assert not hasattr(rag_service, "ChatAnthropic")

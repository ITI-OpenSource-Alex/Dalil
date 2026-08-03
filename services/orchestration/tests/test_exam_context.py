"""
GOA-060 — Exam Context Integration Test Suite

Tests cover:
    1. Unit: real exam bands override self-reported bands in scoring
    2. Unit: intent classifier routes EXAM_PREP correctly
    3. Integration (mocked LLM): EXAM_PREP response references weak area
    4. Integration (mocked LLM): proactive weak-area mention on general question
    5. Unit: Redis caching in fetch_exam_context
    6. Unit: build_supervisor_prompt with and without exam context
"""

import json
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


# ──────────────────────────────────────────────────────────────
# Stub out heavy third-party modules that aren't installed in
# the system Python so we can import app.services.* cleanly.
# ──────────────────────────────────────────────────────────────

def _stub_module(fqn, attrs=None):
    """Register a fake module at *fqn* (dot-separated) if it is missing."""
    if fqn in sys.modules:
        return
    parts = fqn.split(".")
    # Ensure all parent packages exist
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules:
            sys.modules[parent] = types.ModuleType(parent)
    mod = types.ModuleType(fqn)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[fqn] = mod
    # Wire child into parent's namespace
    if len(parts) > 1:
        parent_mod = sys.modules[".".join(parts[:-1])]
        setattr(parent_mod, parts[-1], mod)


class _FakeAsyncRedis:
    @classmethod
    def from_url(cls, *a, **kw):
        return AsyncMock()

# redis.asyncio
_stub_module("redis", {"asyncio": types.ModuleType("redis.asyncio")})
_stub_module("redis.asyncio", {"Redis": _FakeAsyncRedis})

# langchain ecosystem
_stub_module("langchain_anthropic", {"ChatAnthropic": MagicMock()})
_stub_module("langfuse")
_stub_module("langfuse.langchain", {"CallbackHandler": MagicMock()})
_stub_module("langchain")
_stub_module("langchain.memory", {"ConversationBufferWindowMemory": MagicMock()})
_stub_module("langchain_community")
_stub_module("langchain_community.chat_message_histories", {"RedisChatMessageHistory": MagicMock()})

# pybreaker
class _FakeCB:
    def __init__(self, **kw): pass
    current_state = "closed"

class _FakeCBError(Exception): pass

class _FakeListener:
    pass

_stub_module("pybreaker", {
    "CircuitBreaker": _FakeCB,
    "CircuitBreakerError": _FakeCBError,
    "CircuitBreakerListener": _FakeListener,
    "UTC": None,
})

# sse-starlette
_stub_module("sse_starlette")
_stub_module("sse_starlette.sse", {
    "ServerSentEvent": MagicMock(),
    "EventSourceResponse": MagicMock(),
})

# prometheus — metrics stubs need to support .labels().inc() / .observe() chaining
_counter_mock = MagicMock()
_histogram_mock = MagicMock()
_gauge_mock = MagicMock()
_stub_module("prometheus_client", {
    "Counter": lambda *a, **kw: MagicMock(),
    "Histogram": lambda *a, **kw: MagicMock(),
    "Gauge": lambda *a, **kw: MagicMock(),
    "make_asgi_app": MagicMock(),
})

# pydantic_settings (may already exist)
if "pydantic_settings" not in sys.modules:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: F401


# ──────────────────────────────────────────────────────────────
# Shared test data
# ──────────────────────────────────────────────────────────────

MOCK_EXAM_PROFILE = {
    "exam_count": 3,
    "latest_bands": {
        "reading": 7.0,
        "listening": 6.5,
        "writing": 6.0,
        "speaking": 5.5,
    },
    "weak_areas": {
        "speaking": "pronunciation",
        "writing": "task_response",
    },
    "last_exam_date": "2025-07-20T14:30:00Z",
}

MOCK_EXAM_PROFILE_SPEAKING_WEAK = {
    "exam_count": 2,
    "latest_bands": {
        "reading": 7.5,
        "listening": 7.0,
        "writing": 7.0,
        "speaking": 6.0,
    },
    "weak_areas": {
        "speaking": "fluency",
    },
    "last_exam_date": "2025-07-18T10:00:00Z",
}

EMPTY_EXAM_PROFILE = {
    "exam_count": 0,
    "latest_bands": None,
    "weak_areas": None,
    "last_exam_date": None,
}


# ──────────────────────────────────────────────────────────────
# Helper: build a mock structured_llm that returns a given intent
# ──────────────────────────────────────────────────────────────

def _make_llm_mock(intent: str, confidence: float = 0.96):
    from app.services.supervisor import IntentResult

    raw_mock = MagicMock()
    raw_mock.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}

    mock_seq = MagicMock()
    mock_seq.ainvoke = AsyncMock(return_value={
        "parsed": IntentResult(intent=intent, confidence=confidence),
        "raw": raw_mock,
    })
    return mock_seq


# ══════════════════════════════════════════════════════════════
# 1. UNIT — Scoring: real exam bands override self-reported
# ══════════════════════════════════════════════════════════════


class TestScoringBandOverride:
    """Verify that ``compute_opportunity_score`` uses real exam bands over
    self-reported values when both are present."""

    def test_real_bands_override_self_reported(self):
        from app.services.scoring import compute_opportunity_score

        score = compute_opportunity_score(
            self_reported_bands={"reading": 5.0, "listening": 5.0},
            program_requirements={"reading": 7.0, "listening": 7.0},
            real_exam_bands={"reading": 7.0},
        )
        # reading: 7.0/7.0 = 1.0, listening: 5.0/7.0 ≈ 0.7143
        # average ≈ 0.8571
        assert score > 0.85
        assert score < 0.86

    def test_real_bands_fully_override(self):
        from app.services.scoring import compute_opportunity_score

        score = compute_opportunity_score(
            self_reported_bands={"reading": 4.0, "listening": 4.0},
            program_requirements={"reading": 7.0, "listening": 7.0},
            real_exam_bands={"reading": 7.0, "listening": 7.0},
        )
        assert score == 1.0

    def test_no_real_bands_uses_self_reported(self):
        from app.services.scoring import compute_opportunity_score

        score = compute_opportunity_score(
            self_reported_bands={"reading": 7.0},
            program_requirements={"reading": 7.0},
            real_exam_bands=None,
        )
        assert score == 1.0

    def test_merge_bands_prefers_real(self):
        from app.services.scoring import merge_bands

        merged = merge_bands(
            self_reported={"reading": 5.0, "writing": 6.0},
            real_exam_bands={"reading": 7.5},
        )
        assert merged["reading"] == 7.5
        assert merged["writing"] == 6.0

    def test_empty_requirements_returns_perfect(self):
        from app.services.scoring import compute_opportunity_score

        score = compute_opportunity_score(
            self_reported_bands={"reading": 4.0},
            program_requirements={},
        )
        assert score == 1.0

    def test_missing_band_scores_zero_for_skill(self):
        from app.services.scoring import compute_opportunity_score

        score = compute_opportunity_score(
            self_reported_bands={},
            program_requirements={"reading": 7.0, "listening": 7.0},
            real_exam_bands={"reading": 7.0},
        )
        assert score == 0.5


# ══════════════════════════════════════════════════════════════
# 2. UNIT — Intent classifier routes EXAM_PREP correctly
# ══════════════════════════════════════════════════════════════


class TestExamPrepIntentClassification:
    """Verify the supervisor routes skill-improvement queries to EXAM_PREP."""

    @pytest.mark.asyncio
    async def test_improve_reading_routes_exam_prep(self):
        from app.services.supervisor import classify_intent

        mock_seq = _make_llm_mock("EXAM_PREP", 0.96)
        with patch("app.services.supervisor.structured_llm", mock_seq):
            result = await classify_intent("improve my reading score")

        assert result.intent == "EXAM_PREP"
        assert result.confidence >= 0.9
        mock_seq.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_practice_listening_routes_exam_prep(self):
        from app.services.supervisor import classify_intent

        mock_seq = _make_llm_mock("EXAM_PREP", 0.95)
        with patch("app.services.supervisor.structured_llm", mock_seq):
            result = await classify_intent("I want to practice listening")

        assert result.intent == "EXAM_PREP"
        mock_seq.ainvoke.assert_called_once()


# ══════════════════════════════════════════════════════════════
# 3. INTEGRATION — EXAM_PREP response references weak area
# ══════════════════════════════════════════════════════════════


class TestExamPrepResponseIntegration:
    """Simulate a user with exam history hitting an EXAM_PREP intent.

    Verifies the downstream response mentions the weak area, a Cambridge
    test, and a link to /exam.
    """

    @pytest.mark.asyncio
    async def test_exam_prep_mentions_weak_area(self):
        from app.services.client import forward_downstream_stream

        events = []
        async for event in forward_downstream_stream(
            client=AsyncMock(spec=httpx.AsyncClient),
            intent="EXAM_PREP",
            message="I want to improve my speaking",
            user_id="user-123",
            correlation_id="corr-abc",
            exam_context=MOCK_EXAM_PROFILE,
        ):
            events.append(event)

        full_text = "".join(
            e.content for e in events if e.type == "token" and e.content
        )

        assert "pronunciation" in full_text.lower()
        assert "cambridge" in full_text.lower()
        assert "/exam" in full_text
        assert events[-1].type == "exam_prep"

    @pytest.mark.asyncio
    async def test_exam_prep_no_history_suggests_exam(self):
        from app.services.client import forward_downstream_stream

        events = []
        async for event in forward_downstream_stream(
            client=AsyncMock(spec=httpx.AsyncClient),
            intent="EXAM_PREP",
            message="How do I improve my writing?",
            user_id="user-new",
            correlation_id="corr-def",
            exam_context=EMPTY_EXAM_PROFILE,
        ):
            events.append(event)

        full_text = "".join(
            e.content for e in events if e.type == "token" and e.content
        )
        assert "/exam" in full_text


# ══════════════════════════════════════════════════════════════
# 4. INTEGRATION — Proactive weak-area mention on general question
# ══════════════════════════════════════════════════════════════


class TestProactiveWeakAreaMention:
    """Verify that when a user with a weak area asks a general question,
    the system prompt injected into the LLM contains their weakness so the
    model can proactively coach them."""

    def test_prompt_includes_speaking_weakness(self):
        from app.services.supervisor import build_supervisor_prompt

        prompt = build_supervisor_prompt(MOCK_EXAM_PROFILE_SPEAKING_WEAK)

        assert "Speaking: fluency" in prompt
        assert "6.0" in prompt
        assert "PROACTIVE" in prompt

    @pytest.mark.asyncio
    async def test_classify_receives_enriched_prompt(self):
        from app.services.supervisor import classify_intent

        mock_seq = _make_llm_mock("RAG", 0.92)
        with patch("app.services.supervisor.structured_llm", mock_seq):
            result = await classify_intent(
                message="How do I study?",
                exam_context=MOCK_EXAM_PROFILE_SPEAKING_WEAK,
            )

        call_args = mock_seq.ainvoke.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert "Speaking" in system_msg
        assert "fluency" in system_msg
        assert "6.0" in system_msg
        assert result.intent == "RAG"


# ══════════════════════════════════════════════════════════════
# 5. UNIT — Redis caching in fetch_exam_context
# ══════════════════════════════════════════════════════════════


class TestExamContextCaching:
    """Verify fetch_exam_context reads from cache and populates on miss."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_data(self):
        from app.services.exam_context import fetch_exam_context

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(MOCK_EXAM_PROFILE))
        mock_redis.aclose = AsyncMock()

        mock_http = AsyncMock(spec=httpx.AsyncClient)

        result = await fetch_exam_context(mock_http, "user-123", redis_client=mock_redis)

        assert result == MOCK_EXAM_PROFILE
        mock_http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_and_caches(self):
        from app.services.exam_context import fetch_exam_context, CACHE_TTL_SECONDS

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_EXAM_PROFILE
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=mock_response)

        result = await fetch_exam_context(mock_http, "user-456", redis_client=mock_redis)

        assert result == MOCK_EXAM_PROFILE
        mock_http.get.assert_called_once()
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "exam_context:user-456"
        assert call_args[1]["ex"] == CACHE_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_http_failure_returns_none(self):
        from app.services.exam_context import fetch_exam_context

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()

        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await fetch_exam_context(mock_http, "user-789", redis_client=mock_redis)

        assert result is None


# ══════════════════════════════════════════════════════════════
# 6. UNIT — build_supervisor_prompt
# ══════════════════════════════════════════════════════════════


class TestBuildSupervisorPrompt:
    """Verify prompt construction with and without exam context."""

    def test_no_context_returns_base_prompt(self):
        from app.services.supervisor import build_supervisor_prompt, SUPERVISOR_PROMPT

        prompt = build_supervisor_prompt(None)
        assert prompt == SUPERVISOR_PROMPT

    def test_empty_profile_returns_base_prompt(self):
        from app.services.supervisor import build_supervisor_prompt, SUPERVISOR_PROMPT

        prompt = build_supervisor_prompt(EMPTY_EXAM_PROFILE)
        assert prompt == SUPERVISOR_PROMPT

    def test_valid_context_injects_bands(self):
        from app.services.supervisor import build_supervisor_prompt

        prompt = build_supervisor_prompt(MOCK_EXAM_PROFILE)

        assert "7.0" in prompt
        assert "6.5" in prompt
        assert "6.0" in prompt
        assert "5.5" in prompt
        assert "pronunciation" in prompt
        assert "task_response" in prompt
        assert "EXAM_PREP" in prompt
        assert "/exam" in prompt

    def test_includes_exam_prep_intent(self):
        from app.services.supervisor import SUPERVISOR_PROMPT

        assert "EXAM_PREP" in SUPERVISOR_PROMPT

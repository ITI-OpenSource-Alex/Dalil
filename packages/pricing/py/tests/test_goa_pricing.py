import json
import re
from pathlib import Path

import pytest

from goa_pricing import (
    DEFAULT_PRICING_JSON,
    UnpricedModelError,
    cost_usd,
    known_models,
    price_for,
)
from goa_pricing import table as pricing_table

def _find_gateway_config() -> Path | None:
    """Locate services/gateway/config.go, or None when it is not reachable.

    Walks upward instead of indexing `parents[4]`: this package is COPYed into
    container images at paths with a different depth, and a hard index raises
    IndexError during collection -- before the skipif below can decline the
    gateway-parity tests. The tests must be runnable wherever the package lands.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "services" / "gateway" / "config.go"
        if candidate.exists():
            return candidate
    return None


GATEWAY_CONFIG = _find_gateway_config()
REPO_ROOT = GATEWAY_CONFIG.parents[2] if GATEWAY_CONFIG is not None else None


@pytest.fixture(autouse=True)
def _clear_cache():
    pricing_table.reset_cache()
    yield
    pricing_table.reset_cache()


# --- the arithmetic -------------------------------------------------------

def test_cost_matches_hand_computed_value():
    # 2,000 prompt + 300 completion on claude-opus-4-8 at $6/$30 per 1M.
    assert cost_usd("claude-opus-4-8", 2000, 300) == pytest.approx(0.021)


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-opus-4-8", (6.0, 30.0)),
        ("claude-opus-5", (2.0, 10.0)),
        ("gpt-5.6-sol", (6.0, 36.0)),
    ],
)
def test_every_router_model_is_priced(model, expected):
    price = price_for(model)
    assert (price.prompt_per_1m, price.completion_per_1m) == expected


def test_default_table_contains_only_live_router_models():
    assert known_models() == (
        "claude-opus-4-8",
        "claude-opus-5",
        "gpt-5.6-sol",
    )


def test_zero_tokens_costs_zero():
    assert cost_usd("claude-opus-4-8", 0, 0) == 0.0


def test_none_tokens_treated_as_zero():
    assert cost_usd("claude-opus-4-8", None, None) == 0.0


# --- the unpriced-model contract, which is the point of the module --------

def test_unknown_model_returns_none_not_zero(caplog):
    result = cost_usd("some-model-nobody-priced", 1000, 1000)
    assert result is None
    assert result != 0.0, "0.0 makes 'unknown' indistinguishable from 'free' (BUG-055)"
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_price_for_raises_on_unknown_model():
    with pytest.raises(UnpricedModelError) as exc:
        price_for("some-model-nobody-priced")
    # The message must name the fix, not just the failure.
    assert "LLM_PRICING_JSON" in str(exc.value)


# --- configuration --------------------------------------------------------

def test_env_override_is_used(monkeypatch):
    monkeypatch.setenv(
        "LLM_PRICING_JSON",
        '{"my-model":{"prompt_per_1m":1,"completion_per_1m":2}}',
    )
    pricing_table.reset_cache()
    assert cost_usd("my-model", 1_000_000, 1_000_000) == pytest.approx(3.0)


def test_malformed_env_falls_back_to_default_and_logs(monkeypatch, caplog):
    monkeypatch.setenv("LLM_PRICING_JSON", "{not json")
    pricing_table.reset_cache()
    # Still serves the shipped default rather than dying at import.
    assert cost_usd("claude-opus-4-8", 2000, 300) == pytest.approx(0.021)
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_entry_missing_a_field_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("LLM_PRICING_JSON", '{"m":{"prompt_per_1m":1}}')
    pricing_table.reset_cache()
    assert cost_usd("claude-opus-4-8", 2000, 300) == pytest.approx(0.021)
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_cache_follows_env_changes(monkeypatch):
    assert "claude-opus-4-8" in known_models()
    monkeypatch.setenv("LLM_PRICING_JSON", '{"only-this":{"prompt_per_1m":1,"completion_per_1m":1}}')
    assert known_models() == ("only-this",)


# --- the guard that stops this drifting from the Gateway ------------------

def _gateway_default_pricing() -> dict:
    """Extract LLMPricingJSON's `default:"..."` struct tag from the Go source."""
    source = GATEWAY_CONFIG.read_text(encoding="utf-8")
    line = next(ln for ln in source.splitlines() if "LLMPricingJSON" in ln)
    match = re.search(r'default:"(.*)"`', line)
    assert match, f"no default tag found on: {line.strip()}"
    return json.loads(match.group(1).replace('\\"', '"'))


def _env_example_pricing(relative_path: str) -> dict:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    line = next(ln for ln in source.splitlines() if ln.startswith("LLM_PRICING_JSON="))
    return json.loads(line.split("=", 1)[1])


def _compose_default_pricing() -> dict:
    source = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    line = next(ln.strip() for ln in source.splitlines() if "LLM_PRICING_JSON=" in ln)
    raw = line.split("=", 1)[1]
    prefix = "${LLM_PRICING_JSON:-"
    assert raw.startswith(prefix) and raw.endswith("}"), raw
    return json.loads(raw[len(prefix):-1])


@pytest.mark.skipif(GATEWAY_CONFIG is None, reason="gateway source not reachable from this location")
def test_default_table_matches_gateway_exactly():
    """The one test that makes 'one source of truth' true rather than aspirational.

    GOA-135 exists because five sites disagreed about the same numbers. Shipping a
    sixth table that merely happens to agree today would repeat the defect with an
    extra step, so the agreement is asserted rather than commented.
    """
    gateway = _gateway_default_pricing()
    ours = json.loads(DEFAULT_PRICING_JSON)
    assert ours == gateway, (
        "goa_pricing.DEFAULT_PRICING_JSON has drifted from "
        "services/gateway/config.go LLMPricingJSON"
    )


@pytest.mark.skipif(REPO_ROOT is None, reason="repository config mirrors are not reachable")
@pytest.mark.parametrize("relative_path", [".env.example", "services/gateway/.env.example"])
def test_env_example_tables_match_gateway_default(relative_path):
    assert _env_example_pricing(relative_path) == _gateway_default_pricing()


@pytest.mark.skipif(REPO_ROOT is None, reason="docker-compose.yml is not reachable")
def test_compose_table_matches_gateway_default():
    assert _compose_default_pricing() == _gateway_default_pricing()


@pytest.mark.skipif(GATEWAY_CONFIG is None, reason="gateway source not reachable from this location")
def test_gateway_and_python_agree_on_a_real_cost():
    """Parity at the arithmetic level, not just the table level."""
    gateway = _gateway_default_pricing()["claude-opus-4-8"]
    expected = (2000 * gateway["prompt_per_1m"] + 300 * gateway["completion_per_1m"]) / 1_000_000
    assert cost_usd("claude-opus-4-8", 2000, 300) == pytest.approx(expected)


@pytest.mark.skipif(GATEWAY_CONFIG is None, reason="gateway source not reachable from this location")
def test_gateway_fallback_price_matches_our_primary_model():
    """COST_PROMPT_PER_1M/COST_COMPLETION_PER_1M are what the Gateway charges an
    unknown model. They should match the model we actually run, or an unrecognised
    model id silently bills at some other rate."""
    source = GATEWAY_CONFIG.read_text(encoding="utf-8")
    prompt = re.search(r'COST_PROMPT_PER_1M" default:"([\d.]+)"', source)
    completion = re.search(r'COST_COMPLETION_PER_1M" default:"([\d.]+)"', source)
    assert prompt and completion
    price = price_for("claude-opus-4-8")
    assert float(prompt.group(1)) == price.prompt_per_1m
    assert float(completion.group(1)) == price.completion_per_1m


# --- the regression this ticket was opened for ---------------------------

@pytest.mark.parametrize(
    "wrong_prompt,wrong_completion,label",
    [
        (2.0, 10.0, "stale AgentRouter price, 3x under"),
        (0.25, 1.25, "rag: Haiku prices, 8x under"),
        (3.0, 15.0, "writing: Sonnet prices, 1.5x over"),
        (1.0, 5.0, "cv_processor: 2x under"),
        (8.0, 40.0, "ingestion: Opus-4-6 prices, 4x over"),
    ],
)
def test_historical_wrong_prices_are_not_what_we_now_return(wrong_prompt, wrong_completion, label):
    """Each tuple is a price a service really shipped. None may come back."""
    wrong = (2000 * wrong_prompt + 300 * wrong_completion) / 1_000_000
    assert cost_usd("claude-opus-4-8", 2000, 300) != pytest.approx(wrong), label

"""Price table parsing and cost arithmetic. See the package docstring for why."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("goa_pricing")

# Byte-for-byte the default on services/gateway/config.go:76 LLMPricingJSON.
# Kept in sync by tests/test_goa_pricing.py, which parses the Go source and
# compares -- a comment asking two files to agree is not a mechanism.
DEFAULT_PRICING_JSON = (
    '{"claude-opus-4-8":{"prompt_per_1m":6,"completion_per_1m":30},'
    '"claude-opus-5":{"prompt_per_1m":2,"completion_per_1m":10},'
    '"gpt-5.6-sol":{"prompt_per_1m":6,"completion_per_1m":36}}'
)

PRICING_ENV_VAR = "LLM_PRICING_JSON"


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 tokens."""

    prompt_per_1m: float
    completion_per_1m: float


class UnpricedModelError(LookupError):
    """Raised by `price_for` when a model is absent from the table.

    `cost_usd` catches this and returns None instead; the exception exists for
    callers that would rather fail loudly than carry an absent cost.
    """


_cache: Optional[Dict[str, ModelPrice]] = None
_cache_source: Optional[str] = None


def _parse(raw: str) -> Dict[str, ModelPrice]:
    table = json.loads(raw)
    if not isinstance(table, dict):
        raise ValueError(f"{PRICING_ENV_VAR} must be a JSON object, got {type(table).__name__}")

    parsed: Dict[str, ModelPrice] = {}
    for model, entry in table.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{PRICING_ENV_VAR}[{model!r}] must be an object")
        try:
            parsed[model] = ModelPrice(
                prompt_per_1m=float(entry["prompt_per_1m"]),
                completion_per_1m=float(entry["completion_per_1m"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"{PRICING_ENV_VAR}[{model!r}] needs numeric "
                f"prompt_per_1m and completion_per_1m: {exc}"
            ) from exc
    return parsed


def _table() -> Dict[str, ModelPrice]:
    """Parse once per distinct env value.

    Keyed on the raw string rather than cached unconditionally so a test can set
    the variable and see the change without reaching into module internals.
    """
    global _cache, _cache_source

    raw = os.environ.get(PRICING_ENV_VAR) or DEFAULT_PRICING_JSON
    if _cache is not None and _cache_source == raw:
        return _cache

    try:
        parsed = _parse(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        # A malformed override must not silently fall back to defaults that may
        # be wrong for this deployment, nor take the process down at import time.
        # Log loudly, use the shipped default, and let the unpriced-model path
        # surface anything the default does not cover.
        logger.error(
            "invalid %s, falling back to the built-in default table: %s",
            PRICING_ENV_VAR,
            exc,
        )
        parsed = _parse(DEFAULT_PRICING_JSON)

    _cache, _cache_source = parsed, raw
    return parsed


def reset_cache() -> None:
    """Drop the parsed table. For tests that mutate the environment."""
    global _cache, _cache_source
    _cache, _cache_source = None, None


def known_models() -> tuple[str, ...]:
    return tuple(sorted(_table()))


def price_for(model: str) -> ModelPrice:
    """Look up a model's price, raising `UnpricedModelError` if absent."""
    try:
        return _table()[model]
    except KeyError:
        raise UnpricedModelError(
            f"no price for model {model!r}; known models: {', '.join(known_models())}. "
            f"Add it to {PRICING_ENV_VAR} (and to the Gateway's copy)."
        ) from None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """USD for one call, or None when the model is not priced.

    None rather than 0.0 is the whole point -- see the package docstring. Callers
    should record the absent value as absent (a null column, an omitted metric
    label) and increment their unpriced-model counter.
    """
    try:
        price = price_for(model)
    except UnpricedModelError as exc:
        logger.error("%s", exc)
        return None

    return (
        int(input_tokens or 0) * price.prompt_per_1m
        + int(output_tokens or 0) * price.completion_per_1m
    ) / 1_000_000

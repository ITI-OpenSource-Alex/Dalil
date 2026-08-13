"""GOA-030 — the LLM timeout default must match the value that is documented.

`.env.example` has carried this warning since GOA-014:

    Claude Opus via AgentRouter can return extended-thinking blocks; a single
    criterion agent regularly needs 40-90s. At 25s every evaluation lost agents
    to APITimeoutError.

and set ANTHROPIC_TIMEOUT_SECONDS=120. The code default stayed at 25 in two
places, so any deployment that did not set the variable explicitly ran with the
exact value the comment exists to prevent. Measured through the Gateway on
2026-08-11, a 180-word Task 2 essay came back "1 of 4 writing agents failed:
Request timed out".

These tests pin the floor and pin the two defaults to each other. They do not
assert an exact number -- tuning the timeout upward is legitimate; silently
reverting it below the measured agent latency is not.
"""

import importlib
import os
import re
from pathlib import Path

import pytest


# The measured range for one criterion agent is 40-90s (GOA-014, restated in
# .env.example). A ceiling at or below that loses agents on ordinary responses.
MIN_SAFE_TIMEOUT_SECONDS = 90.0


def _find_upwards(name: str) -> Path | None:
    """Locate a repo-root file from wherever the tests happen to be rooted.

    Deliberately not `parents[N]`: in-container the suite lives at /app/tests
    and a fixed index raises IndexError at collection time, which is how
    test_grading_accuracy.py ended up host-only (see the GOA-133-137 handoff).
    """
    for parent in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
        candidate = parent / name
        if candidate.is_file():
            return candidate
    return None


def _fresh_settings(monkeypatch, env_value=None):
    """Build Settings with the env var absent, exercising the code default."""
    from app import config as config_module

    if env_value is None:
        monkeypatch.delenv("ANTHROPIC_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_TIMEOUT_SECONDS", env_value)

    importlib.reload(config_module)
    config_module.get_settings.cache_clear()
    return config_module.get_settings()


def test_default_timeout_survives_a_missing_env_var(monkeypatch):
    settings = _fresh_settings(monkeypatch, env_value=None)
    assert settings.anthropic_timeout_seconds >= MIN_SAFE_TIMEOUT_SECONDS, (
        f"With ANTHROPIC_TIMEOUT_SECONDS unset the service falls back to "
        f"{settings.anthropic_timeout_seconds}s. A single criterion agent is "
        f"measured at 40-90s, so this drops agents on ordinary essays and "
        f"reports it as an agent failure rather than a configuration one."
    )


def test_env_override_is_still_honoured(monkeypatch):
    """The floor is on the DEFAULT, not on what an operator may deliberately set.

    A short timeout is legitimate in a test harness that never calls a provider.
    This asserts the plumbing still works so the guard above cannot be satisfied
    by hardcoding the value.
    """
    settings = _fresh_settings(monkeypatch, env_value="7.5")
    assert settings.anthropic_timeout_seconds == 7.5


def test_code_default_matches_the_documented_default():
    """.env.example is the operator-facing contract; the code must agree with it.

    These two drifted for months in opposite directions, which is why the
    warning comment and the effective behaviour could both be true at once.
    """
    from app import config as config_module

    # Located via the imported module rather than by path arithmetic, so this
    # follows the code wherever it is mounted.
    config_path = Path(config_module.__file__).resolve()

    env_example_path = _find_upwards(".env.example")
    if env_example_path is None:
        # In-container only /app is mounted, so the repo-root file is genuinely
        # absent. Skipping is honest; the guard still runs on a host and in CI,
        # both of which have the full checkout.
        pytest.skip(
            "repo-root .env.example not reachable from this rootdir "
            "(expected in-container, where only /app is mounted)"
        )

    env_example = env_example_path.read_text(encoding="utf-8")
    match = re.search(r"^ANTHROPIC_TIMEOUT_SECONDS=(\d+(?:\.\d+)?)", env_example, re.M)
    assert match, f"{env_example_path} no longer documents ANTHROPIC_TIMEOUT_SECONDS"
    documented = float(match.group(1))

    config_source = config_path.read_text(encoding="utf-8")

    # Both defaults: the dataclass field and the os.getenv fallback. Two
    # defaults for one value is the mechanism that allowed the drift.
    field_default = re.search(
        r"anthropic_timeout_seconds:\s*float\s*=\s*(\d+(?:\.\d+)?)", config_source
    )
    getenv_default = re.search(
        r'os\.getenv\(\s*"ANTHROPIC_TIMEOUT_SECONDS",\s*"(\d+(?:\.\d+)?)"\s*\)',
        config_source,
    )
    assert field_default and getenv_default, "timeout defaults moved; update this guard"

    # The path is in the message on purpose. This value is declared in THREE
    # places -- the repo-root .env.example, services/writing/.env.example and
    # the two code defaults -- and the service-local copy is the one a writing
    # developer actually copies. When they disagree, the first question is
    # always "which file did this read?", and answering it cost real time the
    # first time this fired.
    assert float(field_default.group(1)) == documented, (
        f"Settings default {field_default.group(1)} disagrees with "
        f"{env_example_path}, which says {documented}"
    )
    assert float(getenv_default.group(1)) == documented, (
        f"get_settings() fallback {getenv_default.group(1)} disagrees with "
        f"{env_example_path}, which says {documented}"
    )

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.agents import (
    CRITERIA,
    WritingAgentRunner,
    evaluate_cohesion,
    evaluate_grammar,
    evaluate_task_response,
    evaluate_vocabulary,
)
from app.evaluation import EvaluationCoordinator, calculate_overall_band
from tests.conftest import FakeWritingAgentRunner


@pytest.mark.parametrize(
    ("function", "criterion"),
    [
        (evaluate_task_response, "task_response"),
        (evaluate_cohesion, "cohesion"),
        (evaluate_vocabulary, "vocabulary"),
        (evaluate_grammar, "grammar"),
    ],
)
@pytest.mark.asyncio
async def test_four_public_agent_functions_return_required_contract(function, criterion):
    runner = FakeWritingAgentRunner()

    result = await function("A complete test essay.", "academic_task_2", runner)

    assert result["criterion"] == criterion
    assert set(result) == {
        "criterion",
        "band_score",
        "feedback",
        "improvement_tip",
        "word_count",
        "inline_issues",
    }
    assert len(result["feedback"].split("Sentence-level examples:")[1].splitlines()) == 4


@pytest.mark.asyncio
async def test_coordinator_uses_gather_and_runs_agents_concurrently(monkeypatch):
    runner = FakeWritingAgentRunner(delays={criterion: 0.06 for criterion in CRITERIA})
    coordinator = EvaluationCoordinator(runner)
    real_gather = asyncio.gather
    gather_calls = 0

    async def gather_spy(*args, **kwargs):
        nonlocal gather_calls
        gather_calls += 1
        return await real_gather(*args, **kwargs)

    monkeypatch.setattr("app.evaluation.asyncio.gather", gather_spy)
    started = time.perf_counter()

    summary = await coordinator.evaluate("Test essay text.", "academic_task_2")

    elapsed = time.perf_counter() - started
    assert gather_calls == 1
    assert len(summary.evaluations) == 4
    assert elapsed < 0.16, "four 60ms agents should not take the 240ms sequential time"


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([6.0, 6.0, 6.0, 6.0], 6.0),
        ([6.0, 6.0, 6.0, 7.0], 6.5),
        ([6.5, 6.5, 7.0, 7.0], 7.0),
        ([6.5, 7.0, 7.0, 7.0], 7.0),
    ],
)
def test_overall_score_rounds_to_nearest_half(scores, expected):
    assert calculate_overall_band(scores) == expected


def test_overall_score_requires_all_four_bands():
    with pytest.raises(ValueError, match="exactly four"):
        calculate_overall_band([6.0, 7.0, 8.0])


class FakeMessages:
    def __init__(self, band_score):
        self.band_score = band_score
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        body = {
            "band_score": self.band_score,
            "feedback": "Precise feedback.",
            "improvement_tip": "Vary sentence structure and use precise vocabulary.",
            "sentence_examples": ["Example one.", "Example two.", "Example three."],
            "highlighted_issues": [
                {
                    "text": "word choice",
                    "issue_type": "vocabulary",
                    "suggestion": "precise wording",
                }
            ],
        }
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(body))],
            usage=SimpleNamespace(input_tokens=20, output_tokens=10),
        )


@pytest.mark.parametrize(("raw_band", "expected"), [(-3, 0.0), (9.8, 9.0), (6.24, 6.0)])
@pytest.mark.asyncio
async def test_agent_band_is_clamped_and_rounded(raw_band, expected):
    client = SimpleNamespace(messages=FakeMessages(raw_band))
    runner = WritingAgentRunner(client, model="test-model")
    essay = "This word choice appears in the essay."

    execution = await runner.evaluate("vocabulary", essay, "academic_task_2")

    assert execution.result.band_score == expected
    issue = execution.result.inline_issues[0]
    assert essay[issue.start_char : issue.end_char] == issue.text
    assert 0.0 <= execution.result.band_score <= 9.0


@pytest.mark.asyncio
async def test_agent_uses_configured_output_token_ceiling():
    messages = FakeMessages(6.5)
    client = SimpleNamespace(messages=messages)
    runner = WritingAgentRunner(client, model="test-model", max_tokens=16000)

    await runner.evaluate("cohesion", "A complete sample essay.", "academic_task_2")

    assert messages.calls[0]["max_tokens"] == 16000

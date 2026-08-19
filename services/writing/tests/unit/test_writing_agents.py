import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.agents import (
    CRITERIA,
    SCORE_SYSTEM_PROMPT,
    WritingAgentRunner,
    evaluate_cohesion,
    evaluate_grammar,
    evaluate_task_response,
    evaluate_vocabulary,
)
from app.evaluation import EvaluationCoordinator, calculate_overall_band
from app.ocr_normalization import normalize_essay
from app.writing_rubric import (
    allowed_descriptor_ids,
    descriptors_for,
    render_descriptors,
)
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
        if "frozen decisions" in kwargs["system"]:
            prompt = kwargs["messages"][0]["content"]
            criterion = "cohesion" if "Requested criteria: cohesion" in prompt else "vocabulary"
            body = {
                "evaluations": [
                    {
                        "criterion": criterion,
                        "feedback": "Precise feedback.",
                        "improvement_tip": "Use more precise language.",
                        "sentence_examples": [
                            "Example one.",
                            "Example two.",
                            "Example three.",
                        ],
                        "highlighted_issues": [
                            {
                                "text": "word choice",
                                "issue_type": "vocabulary",
                                "suggestion": "precise wording",
                            }
                        ],
                    }
                ]
            }
        else:
            criterion = next(
                item
                for item in CRITERIA
                if f"criterion={item}" in kwargs["system"]
            )
            body = {
                "band_score": self.band_score,
                "descriptor_id": f"{criterion}.6",
                "confidence": "high",
                "borderline": False,
                "evidence": ["Evidence one", "Evidence two"],
                "lower_band_comparison": "Stronger than the lower band.",
                "higher_band_comparison": "Does not meet the higher band.",
            }
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(body))],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


@pytest.mark.parametrize(("raw_band", "expected"), [(-3, 0.0), (9.8, 9.0), (6.24, 6.0)])
@pytest.mark.asyncio
async def test_agent_band_is_clamped_and_rounded(raw_band, expected):
    client = SimpleNamespace(messages=FakeMessages(raw_band))
    runner = WritingAgentRunner(client, model="claude-opus-5")
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
    runner = WritingAgentRunner(
        client,
        model="claude-opus-5",
        max_tokens=16000,
        score_max_tokens=2500,
        feedback_max_tokens=7000,
        feedback_model="gpt-5.6-sol",
    )

    await runner.evaluate("cohesion", "A complete sample essay.", "academic_task_2")

    assert [call["max_tokens"] for call in messages.calls] == [2500, 7000]
    assert [call["model"] for call in messages.calls] == [
        "claude-opus-5",
        "gpt-5.6-sol",
    ]


def test_scoring_prompt_uses_best_fit_not_conservative_and_every_band():
    assert "conservative" not in SCORE_SYSTEM_PROMPT.lower()
    assert "do not default downward" in SCORE_SYSTEM_PROMPT.lower()
    assert "higher and lower" in SCORE_SYSTEM_PROMPT.lower()
    for criterion in CRITERIA:
        assert set(descriptors_for(criterion, 2)) == set(range(10))
        rendered = render_descriptors(criterion, 2)
        assert "Band 9:" in rendered
        assert "Band 0:" in rendered
        assert len(allowed_descriptor_ids(criterion, 2)) == 10


def test_ocr_normalization_is_opt_in_deterministic_and_maps_offsets():
    original = "| think s0. soft-\nware.\r\n\r\nNext."

    typed = normalize_essay(original, "typed")
    first = normalize_essay(original, "ocr")
    second = normalize_essay(original, "ocr")

    assert typed.text == original
    assert first == second
    assert first.text == "I think so. software.\n\nNext."
    start = first.text.index("I think")
    source_start, source_end = first.original_span(start, start + len("I think"))
    assert original[source_start:source_end] == "| think"


class SequenceMessages:
    def __init__(self, score_bodies):
        self.score_bodies = list(score_bodies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        body = self.score_bodies.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(body))],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def _score_body(band, *, confidence="high", borderline=False):
    return {
        "band_score": band,
        "descriptor_id": f"grammar.{int(band)}",
        "confidence": confidence,
        "borderline": borderline,
        "evidence": ["Evidence one", "Evidence two"],
        "lower_band_comparison": "It exceeds the adjacent lower descriptor.",
        "higher_band_comparison": "It does not meet the adjacent higher descriptor.",
    }


@pytest.mark.asyncio
async def test_selective_ensemble_skips_confident_score():
    messages = SequenceMessages([_score_body(7)])
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages), model="claude-opus-5"
    )

    result = await runner.score(
        "grammar", normalize_essay("A complete sentence."), "academic", task_number=2
    )

    assert result.band_score == 7.0
    assert result.ensemble_used is False
    assert result.model_calls == 1


@pytest.mark.asyncio
async def test_score_rejects_descriptor_id_not_present_in_frozen_rubric():
    body = _score_body(7)
    body["descriptor_id"] = "grammar.42"
    runner = WritingAgentRunner(
        SimpleNamespace(messages=SequenceMessages([body])), model="claude-opus-5"
    )

    with pytest.raises(ValueError, match="unknown descriptor"):
        await runner.score(
            "grammar",
            normalize_essay("A complete sentence."),
            "academic",
            task_number=2,
        )


@pytest.mark.asyncio
async def test_selective_ensemble_adds_second_reader_only_for_borderline_score():
    messages = SequenceMessages(
        [_score_body(6, confidence="medium", borderline=True), _score_body(6.5)]
    )
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages), model="claude-opus-5"
    )

    result = await runner.score(
        "grammar", normalize_essay("A complete sentence."), "academic", task_number=2
    )

    assert result.band_score == 6.5
    assert result.ensemble_used is True
    assert result.model_calls == 2


@pytest.mark.asyncio
async def test_selective_ensemble_adjudicates_large_disagreement():
    messages = SequenceMessages(
        [
            _score_body(6, confidence="low"),
            _score_body(8),
            _score_body(7, confidence="medium"),
        ]
    )
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages), model="claude-opus-5"
    )

    result = await runner.score(
        "grammar", normalize_essay("A complete sentence."), "academic", task_number=2
    )

    assert result.band_score == 7.0
    assert result.ensemble_used is True
    assert result.model_calls == 3


class StagedMessages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if "frozen decisions" in kwargs["system"]:
            body = {
                "evaluations": [
                    {
                        "criterion": criterion,
                        "feedback": f"Focused {criterion} feedback.",
                        "improvement_tip": "Revise one weakness.",
                        "sentence_examples": [
                            "The essay states a position.",
                            "The essay supports an idea.",
                            "The essay reaches a conclusion.",
                        ],
                        "highlighted_issues": [],
                    }
                    for criterion in CRITERIA
                ]
            }
        else:
            criterion = next(
                item
                for item in CRITERIA
                if f"criterion={item}" in kwargs["system"]
            )
            body = _score_body(
                {
                    "task_response": 7,
                    "cohesion": 7,
                    "vocabulary": 6,
                    "grammar": 6,
                }[criterion]
            )
            body["descriptor_id"] = f"{criterion}.{int(body['band_score'])}"
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(body))],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


@pytest.mark.asyncio
async def test_coordinator_separates_four_scores_from_one_combined_feedback_call():
    messages = StagedMessages()
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages),
        model="claude-opus-5",
        selective_ensemble=True,
    )

    summary = await EvaluationCoordinator(runner).evaluate(
        "The essay states a position and supports an idea before it reaches a conclusion.",
        "academic_task_2",
    )

    assert len(messages.calls) == 5
    assert all("frozen decisions" not in call["system"] for call in messages.calls[:4])
    assert "frozen decisions" in messages.calls[-1]["system"]
    assert len(summary.evaluations) == 4
    assert summary.overall_band == 6.5


class FlakyStagedMessages(StagedMessages):
    def __init__(self):
        super().__init__()
        self.grammar_failed = False

    async def create(self, **kwargs):
        if (
            "criterion=grammar" in kwargs["system"]
            and not self.grammar_failed
        ):
            self.grammar_failed = True
            self.calls.append(kwargs)
            raise ConnectionError("transient model gateway failure")
        return await super().create(**kwargs)


@pytest.mark.asyncio
async def test_coordinator_retries_only_the_failed_primary_criterion_once():
    messages = FlakyStagedMessages()
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages), model="claude-opus-5"
    )

    summary = await EvaluationCoordinator(runner).evaluate(
        "The essay states a position and supports an idea before reaching a conclusion.",
        "academic_task_2",
    )

    score_calls = [
        call for call in messages.calls if "frozen decisions" not in call["system"]
    ]
    assert len(score_calls) == 5
    assert sum("criterion=grammar" in call["system"] for call in score_calls) == 2
    assert len(summary.evaluations) == 4


class LowConfidenceStagedMessages(StagedMessages):
    async def create(self, **kwargs):
        response = await super().create(**kwargs)
        if "frozen decisions" not in kwargs["system"]:
            body = json.loads(response.content[0].text)
            body["confidence"] = "low"
            body["borderline"] = True
            response.content[0].text = json.dumps(body)
        return response


@pytest.mark.asyncio
async def test_coordinator_caps_ensemble_to_one_criterion_per_essay():
    messages = LowConfidenceStagedMessages()
    runner = WritingAgentRunner(
        SimpleNamespace(messages=messages),
        model="claude-opus-5",
        max_ensemble_criteria=1,
    )

    await EvaluationCoordinator(runner).evaluate(
        "The essay states a position and supports an idea before reaching a conclusion.",
        "academic_task_2",
    )

    score_calls = [
        call for call in messages.calls if "frozen decisions" not in call["system"]
    ]
    assert len(score_calls) == 5
    assert sum(
        "criterion=task_response" in call["system"] for call in score_calls
    ) == 2
    for criterion in CRITERIA[1:]:
        assert sum(
            f"criterion={criterion}" in call["system"] for call in score_calls
        ) == 1

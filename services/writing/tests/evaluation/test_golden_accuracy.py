import json
import os
from pathlib import Path

import pytest

from app.agents import get_agent_runner
from app.evaluation import EvaluationCoordinator


pytestmark = pytest.mark.evaluation


@pytest.mark.asyncio
async def test_five_essay_golden_accuracy_exceeds_eighty_percent():
    if os.getenv("RUN_WRITING_EVAL") != "1":
        pytest.skip("Set RUN_WRITING_EVAL=1 to run the paid five-essay LLM evaluation")
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is required for the golden evaluation")

    dataset = json.loads(
        (Path(__file__).with_name("golden_essays.json")).read_text(encoding="utf-8")
    )
    assert len(dataset) == 5
    coordinator = EvaluationCoordinator(get_agent_runner())
    matches = 0
    comparisons = 0
    details = []

    for sample in dataset:
        summary = await coordinator.evaluate(
            sample["essay_text"], sample["exam_type"]
        )
        predicted = {item.criterion: item.band_score for item in summary.evaluations}
        sample_matches = {
            criterion: abs(predicted[criterion] - expert_band) <= 0.5
            for criterion, expert_band in sample["expert_bands"].items()
        }
        matches += sum(sample_matches.values())
        comparisons += len(sample_matches)
        details.append(
            {
                "id": sample["id"],
                "predicted": predicted,
                "expert": sample["expert_bands"],
                "within_half_band": sample_matches,
            }
        )

    accuracy = matches / comparisons
    print(json.dumps({"accuracy": accuracy, "details": details}, indent=2))
    assert accuracy > 0.80

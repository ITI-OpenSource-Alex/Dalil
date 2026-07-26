import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from unittest.mock import MagicMock
from evals.judge import (
    load_rubric,
    compute_verdict,
    build_judge_prompt,
    _extract_text,
    _parse_json_object,
    judge_evaluation,
    judge_all,
    JudgeVerdict,
)

def test_judge_prompt_contains_official_descriptors():
    rubric = load_rubric("writing")
    assert "Task Response" in rubric
    agent_eval = {"overall_band": 6.5, "criteria": {"task_response": 6.5}, "justification": "Good essay."}
    prompt = build_judge_prompt("writing", "Sample essay text", agent_eval, rubric)
    assert "OFFICIAL BAND DESCRIPTORS" in prompt
    assert "Task Response" in prompt

def test_judge_all_fails_fast_on_missing_rubric():
    items = [{"id": "w-01", "essay": "text"}]
    agent_results = [{"overall_band": 6.0}]
    with pytest.raises(FileNotFoundError):
        judge_all("unknown_domain_xyz", items, agent_results)

def test_judge_all_asserts_equal_lengths():
    items = [{"id": "w-01", "essay": "text"}, {"id": "w-02", "essay": "text2"}]
    agent_results = [{"overall_band": 6.0}]
    with pytest.raises(AssertionError) as exc_info:
        judge_all("writing", items, agent_results)
    assert "a dropped agent call must be an errored verdict" in str(exc_info.value)

def test_verdict_boundary_cases():
    # Pin exact boundary rule: 0.5 is ACCURATE, 1.0 is OVERSCORED/UNDERSCORED
    assert compute_verdict(6.5, 6.0) == "ACCURATE"
    assert compute_verdict(5.5, 6.0) == "ACCURATE"
    assert compute_verdict(7.0, 6.0) == "OVERSCORED"
    assert compute_verdict(5.0, 6.0) == "UNDERSCORED"

def test_judge_evaluation_cache_and_tokens():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = '{"judged_band": 6.5, "per_criterion": {"task_response": 6.5}, "reason": "Accurate assessment."}'
    mock_response.content = [mock_block]
    mock_usage = MagicMock()
    mock_usage.input_tokens = 450
    mock_usage.output_tokens = 80
    mock_response.usage = mock_usage
    mock_client.messages.create.return_value = mock_response

    item = {
        "id": "w-01",
        "essay": "Test essay unique text 123",
        "expected_band": 6.5,
        "expected_criteria": {"task_response": 6.5}
    }
    agent_result = {"overall_band": 6.5, "criteria": {"task_response": 6.5}}

    res = judge_evaluation("writing", item, agent_result, client=mock_client, use_cache=False)
    assert res.verdict == "ACCURATE"
    assert res.judged_band == 6.5
    assert res.input_tokens == 450
    assert res.output_tokens == 80
    assert res.per_criterion_verdicts["task_response"] == "ACCURATE"

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from evals.consistency import run_consistency, summarise_runs
from evals.judge import JudgeVerdict, get_cache_key, get_model
from evals.report_generator import render_html_report
from evals.runner import (
    ReportMetrics,
    ReportSchema,
    RegressionDeltas,
    check_regression_gate,
    compute_judge_family_delta,
    load_golden_dataset,
    run_speaking_eval,
    run_writing_consistency,
    run_writing_eval,
)
from evals.ws_client import SpeakingWsClient


GOLDEN_PATH = Path(__file__).parent.parent / "golden_dataset.json"


def _verdict(item_id: str, model: str) -> JudgeVerdict:
    return JudgeVerdict(
        item_id=item_id,
        verdict="ACCURATE",
        agent_band=6.0,
        expert_band=6.0,
        delta=0.0,
        reason=f"judged by {model}",
        judged_band=6.5 if model.startswith("gpt-") else 6.0,
    )


def _mixed_dataset() -> dict:
    return {
        "writing": [
            {
                "id": "validated",
                "essay": "Validated essay",
                "expected_band": 6.0,
                "expected_criteria": {},
                "band_source": "examiner",
                "label_validated": True,
            },
            {
                "id": "synthetic",
                "essay": "Synthetic essay",
                "expected_band": 9.0,
                "expected_criteria": {},
                "band_source": "SYNTHETIC — generated",
                "label_validated": False,
            },
        ]
    }


def test_judge_model_defaults_to_non_grader_family(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("WRITING_MODEL", raising=False)
    assert get_model() == "gpt-5.6-sol"
    assert not get_model().startswith("claude-")


def test_judge_model_recorded_in_report():
    report = ReportSchema(
        run_id="1",
        metrics=ReportMetrics(),
        judge_model="gpt-5.6-sol",
        grader_models=["claude-opus-5"],
        regression_vs_previous=RegressionDeltas(),
        timestamp="2026-08-08T00:00:00Z",
        git_sha="abc",
    ).model_dump()
    assert report["judge_model"] == "gpt-5.6-sol"
    assert report["grader_models"] == ["claude-opus-5"]


def test_judge_family_delta_present_when_both_arms_run(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "evals.runner._request_writing",
        lambda *_args, **_kwargs: {
            "overall_band": 6.0,
            "criteria": {},
            "from_cache": False,
        },
    )

    def fake_judge_all(_domain, items, _results, **kwargs):
        calls.append(kwargs["model"])
        return [_verdict(item["id"], kwargs["model"]) for item in items]

    monkeypatch.setattr("evals.runner.judge_all", fake_judge_all)
    result = run_writing_eval(_mixed_dataset())

    assert set(calls) == {"claude-opus-5", "gpt-5.6-sol"}
    assert set(result["judge_arms"]) == {"same_family", "independent"}
    assert result["judge_family_delta"]["judged_band_deltas"] == {
        "validated": 0.5
    }


def test_consistency_computes_spread():
    bands = [6.0, 6.5, 7.0, 6.5, 6.0]
    rows = [
        {
            "item_id": "w-1",
            "repeat": index,
            "result": {
                "overall_band": band,
                "criteria": {"grammar": band},
            },
        }
        for index, band in enumerate(bands, 1)
    ]
    result = summarise_runs(rows, repeats=5)
    item = result["per_item"]["w-1"]
    assert item["max_spread"] == 1.0
    assert item["std_dev"] == round(0.37416573867739417, 4)
    assert item["modal_band"] == 6.0
    assert item["modal_tie"] is True
    assert result["domain"]["unanimous_rate"] == 0.0


def test_consistency_unanimous_case():
    rows = [
        {
            "item_id": "w-1",
            "repeat": index,
            "result": {"overall_band": 6.5, "criteria": {"grammar": 6.5}},
        }
        for index in range(1, 6)
    ]
    result = summarise_runs(rows, repeats=5)
    assert result["per_item"]["w-1"]["std_dev"] == 0.0
    assert result["domain"]["unanimous_rate"] == 1.0


def test_judge_cache_key_varies_with_agent_band():
    keys = {
        get_cache_key("writing", "same essay", band, "gpt-5.6-sol")
        for band in (5.0, 5.5, 6.0, 6.5, 7.0)
    }
    assert len(keys) == 5


def test_accuracy_excludes_unvalidated_rows(monkeypatch):
    requested = []

    def fake_request(item, **_kwargs):
        requested.append(item["id"])
        return {"overall_band": 6.0, "criteria": {}, "from_cache": False}

    monkeypatch.setattr("evals.runner._request_writing", fake_request)
    monkeypatch.setattr(
        "evals.runner.judge_all",
        lambda _domain, items, _results, **kwargs: [
            _verdict(item["id"], kwargs["model"]) for item in items
        ],
    )
    result = run_writing_eval(_mixed_dataset())
    assert requested == ["validated"]
    assert result["writing_n_validated"] == 1
    assert result["writing_accuracy"] == 1.0


def test_small_n_forces_caveat(monkeypatch):
    monkeypatch.setattr(
        "evals.runner._request_writing",
        lambda *_args, **_kwargs: {
            "overall_band": 6.0,
            "criteria": {},
            "from_cache": False,
        },
    )
    monkeypatch.setattr(
        "evals.runner.judge_all",
        lambda _domain, items, _results, **kwargs: [
            _verdict(item["id"], kwargs["model"]) for item in items
        ],
    )
    result = run_writing_eval(_mixed_dataset())
    assert result["accuracy_caveat"] == (
        "n=1 — not a validation; see band_source"
    )


def test_report_renders_caveat_adjacent_to_accuracy():
    caveat = "n=3 — not a validation; see band_source"
    html = render_html_report(
        {
            "run_id": "r",
            "git_sha": "abc",
            "timestamp": "now",
            "metrics": {
                "writing_n_validated": 3,
                "accuracy_caveat": caveat,
            },
        },
        {"writing": {"accuracy": 2 / 3}},
    )
    soup = BeautifulSoup(html, "html.parser")
    value = soup.select_one(".stat-val")
    assert value.find_next_sibling().get_text(strip=True) == caveat


def test_synthetic_rows_are_never_validated():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for domain in ("writing", "writing_synthetic_unvalidated", "speaking"):
        for row in data[domain]:
            assert "band_source" in row
            assert "label_validated" in row
            if row["band_source"].startswith("SYNTHETIC"):
                assert row["label_validated"] is False


def test_provenance_block_in_report():
    data = load_golden_dataset(str(GOLDEN_PATH))
    for domain in ("writing", "writing_synthetic_unvalidated", "speaking"):
        assert set(data["provenance"][domain]) == {
            "n_total",
            "n_validated",
            "n_synthetic",
            "band_source",
        }


@pytest.mark.asyncio
async def test_ws_client_returns_none_on_failure():
    client = SpeakingWsClient(ws_url="ws://unreachable")
    with patch("websockets.connect", side_effect=OSError("refused")):
        result = await client.evaluate_transcript("text")
    assert result["overall_band"] is None
    assert result["overall_band"] != 0.0


@pytest.mark.asyncio
async def test_ws_client_returns_none_on_timeout():
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=ws)
    context.__aexit__ = AsyncMock(return_value=None)
    with patch("websockets.connect", return_value=context):
        result = await SpeakingWsClient("ws://gateway").evaluate_transcript("text")
    assert result["overall_band"] is None
    assert result["overall_band"] != 0.0


def test_ws_client_default_url_is_reachable_shape(monkeypatch):
    monkeypatch.delenv("SPEAKING_WS_URL", raising=False)
    url = SpeakingWsClient().ws_url
    assert url == "ws://localhost:8080/api/speaking/ws"
    assert ":8002" not in url


def test_speaking_eval_never_fabricates():
    result = run_speaking_eval({"speaking": []})
    assert result["speaking_accuracy"] is None
    assert result["speaking_pipeline_exercised"] is False
    assert "not measured" in result["speaking_reason"]
    assert not any(isinstance(value, (int, float)) for key, value in result.items()
                   if key == "speaking_accuracy")


def test_compare_with_flags_consistency_regression():
    current = {"writing": {"accuracy": 0.9, "judged": 10, "errored": 0, "accurate": 9}}
    consistency = {"writing": {"domain": {"std_dev": 0.3}}}
    previous_consistency = {"writing": {"domain": {"std_dev": 0.1}}}
    passed, failures = check_regression_gate(
        current, None, consistency, previous_consistency
    )
    assert not passed
    assert any("CONSISTENCY REGRESSION" in failure for failure in failures)


def test_consistency_submission_types_are_unique_and_schema_safe(monkeypatch):
    submission_types = []

    def fake_request(_item, *, submission_type, **_kwargs):
        submission_types.append(submission_type)
        return {"overall_band": 6.0, "criteria": {}, "from_cache": False}

    monkeypatch.setattr("evals.runner._request_writing", fake_request)
    monkeypatch.setattr(
        "evals.runner.run_consistency",
        lambda items, evaluator, **kwargs: {
            "results": [
                evaluator(item, repeat, kwargs["user_id"])
                for item in items
                for repeat in range(1, kwargs["repeats"] + 1)
            ]
        },
    )
    run_writing_consistency(_mixed_dataset(), repeats=5)
    assert len(submission_types) == len(set(submission_types)) == 5
    assert max(map(len, submission_types)) <= 64


def test_incomplete_consistency_is_a_coverage_failure():
    current = {"writing": {"accuracy": 0.9, "judged": 10, "errored": 0, "accurate": 9}}
    incomplete = {"writing": {"n_calls": 0, "expected_calls": 15, "domain": {}}}
    passed, failures = check_regression_gate(current, None, incomplete, None)
    assert not passed
    assert any("CONSISTENCY COVERAGE" in failure for failure in failures)


def test_consistency_cache_bypass_and_unknown_cost_are_explicit():
    submission_calls = []

    def evaluator(item, repeat, user_id):
        submission_calls.append((item["id"], repeat, user_id))
        return {"overall_band": 6.0, "criteria": {}, "from_cache": False}

    result = run_consistency(
        [{"id": "w-1"}],
        evaluator,
        repeats=5,
        user_id="telemetry-user",
        model="claude-opus-5",
        telemetry_reader=lambda *_: {
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
            "reason": "telemetry unavailable",
        },
    )
    assert len(submission_calls) == 5
    assert result["n_calls"] == 5
    assert result["cost"]["cost_usd"] is None
    assert result["cost"]["reason"]

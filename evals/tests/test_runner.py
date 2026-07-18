import pytest
import os
import sys
import json
from unittest.mock import patch, MagicMock, mock_open

# Adjust path to import the runner script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from runner import (
    ReportSchema, 
    ReportMetrics, 
    RegressionDeltas, 
    run_scoring_eval, 
    run_speaking_eval, 
    run_writing_eval,
    run_rag_eval,
    load_golden_dataset,
    main
)

@pytest.fixture
def valid_dataset():
    return {
        "rag": [{"question": "q1", "expected_answer_concepts": ["a1"]}],
        "scoring": [{"profile": "p1", "expected_gate": "pass", "expected_soft_score": 85}],
        "speaking": [{"transcript": "t1", "expected_band": 7.5}],
        "writing": [{"essay": "e1", "expected_band": 6.5}]
    }

# --- 1. Smoke test ---
def test_1_smoke_report_schema():
    """Test 1: Report schema constructs successfully with valid inputs"""
    metrics = ReportMetrics(
        rag_accuracy=1.0, 
        gate_accuracy=1.0, 
        scoring_mae=2.5, 
        speaking_accuracy=0.8, 
        writing_accuracy=0.8
    )
    deltas = RegressionDeltas(
        delta_rag=0.0, 
        delta_gate=0.0, 
        delta_scoring_mae=0.0, 
        delta_speaking=0.0, 
        delta_writing=0.0
    )
    report = ReportSchema(
        run_id="test", 
        metrics=metrics, 
        regression_vs_previous=deltas, 
        timestamp="now", 
        git_sha="sha"
    )
    assert report.metrics.rag_accuracy == 1.0


# --- 2. MAE arithmetic for soft scores ---
@patch("runner.httpx.post")
def test_2_mae_calculation(mock_post):
    """Test 2: Verifies the scoring_mae calculations using real response payload shapes"""
    data = {"scoring": [
        {"profile": "p1", "expected_gate": "pass", "expected_soft_score": 85},
        {"profile": "p2", "expected_gate": "blocked", "expected_soft_score": 90},
        {"profile": "p3", "expected_gate": "pass", "expected_soft_score": 70}
    ]}
    
    responses = [
        MagicMock(json=lambda: {"blocked_by": None, "score": 80}),
        MagicMock(json=lambda: {"blocked_by": "gpa", "score": 92}),
        MagicMock(json=lambda: {"blocked_by": None, "score": 70}),
    ]
    mock_post.side_effect = responses
    
    result = run_scoring_eval(data)
    assert abs(result["scoring_mae"] - 2.333) < 0.01
    assert result["gate_accuracy"] == 1.0


# --- 3. Pass-rate aggregation boundary ---
@patch("runner.httpx.post")
def test_3_pass_rate_aggregation_writing(mock_post):
    """Test 3: Validates pass-rate aggregation boundaries on Writing eval"""
    data = {"writing": [
        {"essay": f"e{i}", "expected_band": 7.0} for i in range(5)
    ]}
    
    # 4 passes (score within 0.5), 1 fail (score off by 1.0)
    mock_post.side_effect = [
        MagicMock(json=lambda: {"overall_band": 7.5}), # Pass
        MagicMock(json=lambda: {"overall_band": 7.0}), # Pass
        MagicMock(json=lambda: {"overall_band": 6.5}), # Pass
        MagicMock(json=lambda: {"overall_band": 7.0}), # Pass
        MagicMock(json=lambda: {"overall_band": 5.0}), # Fail
    ]
    
    result = run_writing_eval(data)
    assert result["writing_accuracy"] == 0.8


# --- 4 & 5. Absolute threshold gate & Regression gate ---
@patch("runner.sys.exit")
@patch("runner.run_writing_eval")
@patch("runner.run_speaking_eval")
@patch("runner.run_scoring_eval")
@patch("runner.run_rag_eval")
@patch("runner.load_previous_report")
@patch("runner.load_golden_dataset")
def test_4_and_5_gates(mock_load_ds, mock_load_prev, mock_rag, mock_score, mock_speak, mock_write, mock_exit):
    """Test 4 & 5: Verifies failure on absolute drops and regressions"""
    mock_load_ds.return_value = {"dummy": "data"}
    mock_rag.return_value = {"rag_accuracy": 1.0}
    mock_score.return_value = {"gate_accuracy": 1.0, "scoring_mae": 2.0}
    mock_speak.return_value = {"speaking_accuracy": None} # Skipped
    mock_write.return_value = {"writing_accuracy": 1.0}
    
    mock_load_prev.return_value = {}
    
    def mock_exit_func(code):
        raise SystemExit(code)
    mock_exit.side_effect = mock_exit_func
    
    # Happy path
    with patch("runner.argparse.ArgumentParser.parse_args", return_value=MagicMock(compare_with=None, s3_upload_path=None)):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0

    # Test 4: Absolute threshold failure (RAG < 0.8)
    mock_rag.return_value = {"rag_accuracy": 0.79}
    with patch("runner.argparse.ArgumentParser.parse_args", return_value=MagicMock(compare_with=None, s3_upload_path=None)):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1

    # Test 5: Regression failure (Writing drops > 0.05)
    mock_rag.return_value = {"rag_accuracy": 1.0}
    mock_write.return_value = {"writing_accuracy": 0.90}
    mock_load_prev.return_value = {
        "metrics": {
            "rag_accuracy": 1.0,
            "gate_accuracy": 1.0,
            "scoring_mae": 2.0,
            "speaking_accuracy": None,
            "writing_accuracy": 1.0
        }
    }
    with patch("runner.argparse.ArgumentParser.parse_args", return_value=MagicMock(compare_with="prev.json", s3_upload_path=None)):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1

# --- 6. No previous report bootstrap ---
@patch("runner.sys.exit")
@patch("runner.run_writing_eval")
@patch("runner.run_speaking_eval")
@patch("runner.run_scoring_eval")
@patch("runner.run_rag_eval")
@patch("runner.load_previous_report")
@patch("runner.load_golden_dataset")
def test_6_no_previous_report(mock_load_ds, mock_load_prev, mock_rag, mock_score, mock_speak, mock_write, mock_exit):
    """Test 6: Validates it doesn't crash when compare-with is omitted (bootstrap)"""
    mock_load_ds.return_value = {"dummy": "data"}
    mock_rag.return_value = {"rag_accuracy": 1.0}
    mock_score.return_value = {"gate_accuracy": 1.0, "scoring_mae": 2.0}
    mock_speak.return_value = {"speaking_accuracy": None}
    mock_write.return_value = {"writing_accuracy": 1.0}
    
    def mock_exit_func(code):
        raise SystemExit(code)
    mock_exit.side_effect = mock_exit_func
    
    with patch("runner.argparse.ArgumentParser.parse_args", return_value=MagicMock(compare_with=None, s3_upload_path=None)):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0
        mock_load_prev.assert_not_called()

# --- 7. Missing API key / Schema Validation (Combined) ---
def test_7_malformed_dataset():
    """Test 7: RAG eval handles malformed schema inputs (pydantic rejection)"""
    with patch("builtins.open", mock_open(read_data='{"rag": [{"question": "q1"}]}')):
        dataset = load_golden_dataset("dummy.json")
        assert dataset is None

# --- 8. S3 Upload mock validation ---
@patch("runner.sys.exit")
@patch("runner.boto3.client")
@patch("runner.run_writing_eval")
@patch("runner.run_speaking_eval")
@patch("runner.run_scoring_eval")
@patch("runner.run_rag_eval")
@patch("runner.load_golden_dataset")
def test_8_s3_upload(mock_load_ds, mock_rag, mock_score, mock_speak, mock_write, mock_boto, mock_exit):
    """Test 8: Ensure boto3 is called correctly when S3 upload path is given"""
    mock_load_ds.return_value = {"dummy": "data"}
    mock_rag.return_value = {"rag_accuracy": 1.0}
    mock_score.return_value = {"gate_accuracy": 1.0, "scoring_mae": 2.0}
    mock_speak.return_value = {"speaking_accuracy": None}
    mock_write.return_value = {"writing_accuracy": 1.0}
    
    mock_s3 = MagicMock()
    mock_boto.return_value = mock_s3
    
    def mock_exit_func(code):
        raise SystemExit(code)
    mock_exit.side_effect = mock_exit_func
    
    with patch("runner.argparse.ArgumentParser.parse_args", return_value=MagicMock(compare_with=None, s3_upload_path="s3://goa-eval-reports/")):
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 0
        mock_boto.assert_called_with('s3', endpoint_url=os.environ.get('AWS_ENDPOINT_URL'))
        
        # Verify upload_file was called with the correct bucket and a .json key
        mock_s3.upload_file.assert_called_once()
        args, kwargs = mock_s3.upload_file.call_args
        assert args[1] == "goa-eval-reports"
        assert args[2].endswith(".json")

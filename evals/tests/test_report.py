import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from evals.report_generator import render_html_report
from evals.judge import JudgeVerdict

def test_report_renders_all_sections():
    report_dict = {
        "run_id": "test_run_123",
        "git_sha": "abc1234",
        "timestamp": "2026-07-25T12:00:00Z"
    }
    domain_stats = {
        "writing": {"accuracy": 0.85},
        "speaking": {"accuracy": None}
    }
    writing_mae = {
        "overall": 0.25,
        "per_criterion": {"task_response": 0.25, "coherence": 0.25}
    }
    writing_verdicts = [
        JudgeVerdict(item_id="w-01", verdict="ACCURATE", agent_band=6.5, expert_band=6.5, delta=0.0, reason="Good response", judged_band=6.5)
    ]

    html = render_html_report(report_dict, domain_stats, writing_mae, writing_verdicts)
    assert "GOA Evaluation Pipeline Report" in html
    assert "test_run_123" in html
    assert "85.0%" in html
    assert "PASS (Target: 80%)" in html
    assert "NOT MEASURED" in html
    assert "Task Response" in html
    assert "w-01" in html

def test_report_shows_failing_badge_when_below_target():
    report_dict = {"run_id": "fail_run", "git_sha": "def5678", "timestamp": "2026-07-25T12:00:00Z"}
    domain_stats = {"writing": {"accuracy": 0.70}}
    html = render_html_report(report_dict, domain_stats)
    assert "70.0%" in html
    assert "FAIL (Below 80%)" in html

def test_report_marks_unmeasured_domain_explicitly():
    report_dict = {"run_id": "unmeasured_run", "git_sha": "xyz", "timestamp": "2026-07-25T12:00:00Z"}
    domain_stats = {"speaking": {"accuracy": None}}
    html = render_html_report(report_dict, domain_stats)
    assert "NOT MEASURED" in html

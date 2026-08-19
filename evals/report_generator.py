from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

def render_html_report(report_dict: dict, domain_stats: dict, writing_mae: dict = None, writing_verdicts: list = None) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html.j2")
    report_view = {
        "judge_model": None,
        "grader_models": [],
        "provenance": {},
        "judge_family_delta": {},
        "consistency": {},
        **report_dict,
    }
    report_view["metrics"] = {
        "writing_n_validated": 0,
        "accuracy_caveat": None,
        "speaking_reason": None,
        **(report_dict.get("metrics") or {}),
    }
    return template.render(
        report=report_view,
        domain_stats=domain_stats,
        writing_mae=writing_mae or {},
        writing_verdicts=writing_verdicts or [],
        judge_model=report_view["judge_model"],
        grader_models=report_view["grader_models"],
    )

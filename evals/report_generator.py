from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from evals.judge import get_model

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

def render_html_report(report_dict: dict, domain_stats: dict, writing_mae: dict = None, writing_verdicts: list = None) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html.j2")
    return template.render(
        report=report_dict,
        domain_stats=domain_stats,
        writing_mae=writing_mae or {},
        writing_verdicts=writing_verdicts or [],
        judge_model=get_model()
    )

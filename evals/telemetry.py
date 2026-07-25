import os
from typing import Dict, Any, List

def export_prometheus_metrics(domain: str, accuracy_stats: dict, mae_stats: dict):
    """Expose Prometheus gauges for eval accuracy and criterion MAE."""
    try:
        from prometheus_client import Gauge, collector
        
        # Singleton pattern for Prometheus gauges
        if not hasattr(export_prometheus_metrics, "gauge_accuracy"):
            export_prometheus_metrics.gauge_accuracy = Gauge(
                "goa_eval_judge_accuracy",
                "Judge accuracy per domain",
                ["domain"]
            )
            export_prometheus_metrics.gauge_mae = Gauge(
                "goa_eval_criterion_mae",
                "Criterion Mean Absolute Error per domain",
                ["domain", "criterion"]
            )
            
        acc = accuracy_stats.get("accuracy")
        if acc is not None:
            export_prometheus_metrics.gauge_accuracy.labels(domain=domain).set(acc)
            
        for crit, mae_val in (mae_stats.get("per_criterion") or {}).items():
            export_prometheus_metrics.gauge_mae.labels(domain=domain, criterion=crit).set(mae_val)
    except Exception as e:
        print(f"Prometheus metric export skipped: {e}")

def annotate_langfuse_trace(trace_id: str, verdict: str, reason: str, score_delta: float):
    """Annotate Langfuse trace with judge verdict and reason."""
    langfuse_pk = os.environ.get("LANGFUSE_PUBLIC_KEY")
    langfuse_sk = os.environ.get("LANGFUSE_SECRET_KEY")
    if not (langfuse_pk and langfuse_sk and trace_id):
        return
    try:
        from langfuse import Langfuse
        langfuse = Langfuse()
        langfuse.score(
            trace_id=trace_id,
            name="judge_verdict",
            value=1.0 if verdict == "ACCURATE" else 0.0,
            comment=f"Verdict: {verdict}. Delta: {score_delta}. Reason: {reason}"
        )
    except Exception as e:
        print(f"Langfuse trace annotation skipped: {e}")

def format_pr_comment(metrics: dict, deltas: dict, failures: List[str]) -> str:
    """Format markdown PR comment for GitHub actions workflow."""
    status_badge = "![PASS](https://img.shields.io/badge/evals-PASS-success)" if not failures else "![FAIL](https://img.shields.io/badge/evals-FAIL-critical)"
    
    lines = [
        f"### 🧪 GOA Evaluation Pipeline Results {status_badge}",
        "",
        "| Domain | Accuracy | Target | Delta vs Prev | Status |",
        "|---|---|---|---|---|"
    ]
    
    for domain in ("writing", "speaking", "rag", "gate"):
        acc = metrics.get(f"{domain}_accuracy")
        if acc is not None:
            acc_str = f"{acc * 100:.1f}%"
            target_str = "80%"
            delta_val = deltas.get(f"delta_{domain}")
            delta_str = f"{delta_val * 100:+.1f}%" if delta_val is not None else "N/A"
            badge = "✅ PASS" if acc >= 0.80 else "❌ FAIL"
        else:
            acc_str = "N/A"
            target_str = "80%"
            delta_str = "N/A"
            badge = "⚪ UNMEASURED"
            
        lines.append(f"| **{domain.upper()}** | {acc_str} | {target_str} | {delta_str} | {badge} |")
        
    if failures:
        lines.extend(["", "#### ⚠️ Gate Failure Reasons:"])
        for f in failures:
            lines.append(f"- {f}")
            
    return "\n".join(lines)

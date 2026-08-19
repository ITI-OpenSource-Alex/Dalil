import pytest

from evals import rag_benchmark


def test_benchmark_refuses_to_report_when_reranker_degraded(monkeypatch):
    monkeypatch.setattr(
        rag_benchmark, "fetch_live_rerank_mode", lambda: "DEGRADED-fallback"
    )
    with pytest.raises(rag_benchmark.BenchmarkEnvironmentError, match="validity gate"):
        rag_benchmark.run_arm(
            "full",
            [],
            {
                "document_count": 1,
                "content_hash": "measured",
                "snapshot_path": "snapshot.jsonl.gz",
                "snapshot_sha256": "measured",
                "index_reloptions": "{lists=100}",
                "ivfflat_probes_session_default": 1,
            },
        )

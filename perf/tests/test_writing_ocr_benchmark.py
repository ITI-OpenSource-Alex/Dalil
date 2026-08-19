from __future__ import annotations

from argparse import Namespace

from perf import writing_ocr_benchmark as benchmark


def test_all_ocr_samples_are_anchored_to_examiner_bands_without_commentary():
    samples = [benchmark.extract_sample(spec) for spec in benchmark.SAMPLES]

    assert [sample.spec.published_band for sample in samples] == [
        7.0,
        6.0,
        4.5,
        7.0,
        4.0,
        6.5,
    ]
    assert all(sample.word_count >= 150 for sample in samples)
    assert all("This response" not in sample.essay for sample in samples)
    assert all("examiner" not in sample.essay.lower() for sample in samples)


def test_aggregate_reports_agreement_error_bias_and_nearest_rank_latency():
    rows = [
        {
            "delta": 0.0,
            "absolute_error": 0.0,
            "exact": True,
            "within_half_band": True,
            "within_one_band": True,
            "latency_ms": 100.0,
        },
        {
            "delta": 0.5,
            "absolute_error": 0.5,
            "exact": False,
            "within_half_band": True,
            "within_one_band": True,
            "latency_ms": 200.0,
        },
        {
            "delta": -1.5,
            "absolute_error": 1.5,
            "exact": False,
            "within_half_band": False,
            "within_one_band": False,
            "latency_ms": 300.0,
        },
    ]

    metrics = benchmark.aggregate(rows, [])

    assert metrics == {
        "n_total": 3,
        "n_scored": 3,
        "n_failed": 0,
        "exact_agreement": 0.3333,
        "within_half_band": 0.6667,
        "within_one_band": 0.6667,
        "mae": 0.6667,
        "rmse": 0.9129,
        "mean_signed_error": -0.3333,
        "latency_ms": {"median": 200.0, "p95": 300.0, "max": 300.0},
    }


def test_dry_run_writes_no_essay_text_to_report(tmp_path):
    output = tmp_path / "report.json"
    report, written = benchmark.run(
        Namespace(
            writing_url="http://unused",
            timeout=1.0,
            model="test-model",
            output=str(output),
            dry_run=True,
        )
    )

    assert written == output
    assert report["valid"] is True
    assert report["samples"] == []
    assert all("essay" not in row for row in report["dataset_manifest"])
    assert "The table depicts" not in output.read_text(encoding="utf-8")


def test_live_request_marks_book_text_as_ocr(monkeypatch):
    captured = {}

    class Response:
        is_error = False

        @staticmethod
        def json():
            return {
                "overall_band": 6.5,
                "from_cache": False,
                "evaluations": [
                    {"criterion": criterion, "band_score": 6.5}
                    for criterion in (
                        "task_response",
                        "cohesion",
                        "vocabulary",
                        "grammar",
                    )
                ],
            }

    def fake_post(url, *, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr(benchmark.httpx, "post", fake_post)
    sample = benchmark.extract_sample(benchmark.SAMPLES[0])

    benchmark.score_sample(
        sample,
        writing_url="http://writing.test",
        timeout_seconds=12.0,
    )

    assert captured["json"]["inputSource"] == "ocr"
    assert captured["json"]["essayText"] == sample.essay

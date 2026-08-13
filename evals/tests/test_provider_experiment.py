"""SPEAK-EVAL-011 — the provider experiment.

Acceptance:

  - the Go speaking service does not become Gladia-coupled;
  - provider selection is configured and recorded in provenance;
  - the experiment cannot mutate the frozen human labels;
  - production rollout requires an approved comparison report.

The first is the one that matters architecturally and it is asserted against the
Go source, because it is a property of what is NOT there. Go must be able to
compile, run and pass with no knowledge that Gladia exists. If the provider ever
leaks across /stt, the experiment has failed regardless of which engine scores
better, because the next provider change becomes a change to a scoring service.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _load_speech_providers():
    """Load the sidecar's providers module WITHOUT claiming the name `app`.

    Putting services/speech on sys.path registers its `app` package globally,
    and the next test that imports `app` from a different service gets this one
    -- which is how a passing suite started failing with ModuleNotFoundError in
    a test that has nothing to do with speech.

    Several services each have a top-level `app`; the name is not ours to take.
    """
    import importlib.util

    name = "goa_speech_providers"
    path = REPO / "services" / "speech" / "app" / "providers.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)

    # Registered BEFORE exec, under its own unique name. @dataclass resolves
    # field types via sys.modules[cls.__module__], so an unregistered module
    # makes that lookup return None. The name is distinctive precisely so this
    # registration cannot collide with any service's `app`.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_providers = _load_speech_providers()

FasterWhisperProvider = _providers.FasterWhisperProvider
Transcription = _providers.Transcription
Word = _providers.Word
build_provider = _providers.build_provider
configured_provider_name = _providers.configured_provider_name
normalise_gladia = _providers.normalise_gladia
from evals.speaking.provider_comparison import (  # noqa: E402
    ComparisonReport,
    compare_transcriptions,
    count_fillers,
    word_error_rate,
)


# --- the Go service must not know Gladia exists -----------------------------

GO_SPEAKING = REPO / "services" / "speaking"


def go_sources() -> list[Path]:
    return [
        path
        for path in GO_SPEAKING.rglob("*.go")
        # cmd/contract-digest and the eval-only tooling are not the service.
        if "testdata" not in path.parts
    ]


def test_the_go_speaking_service_never_mentions_gladia():
    offenders = []
    for path in go_sources():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "gladia" in text:
            offenders.append(str(path.relative_to(REPO)))

    assert offenders == [], (
        "the speaking service references Gladia: "
        + ", ".join(offenders)
        + ". Provider choice belongs behind /stt; a scoring service that knows "
        "the engine's name will need changing the next time the engine changes."
    )


def test_the_go_service_holds_no_provider_credential():
    offenders = []
    for path in go_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "GLADIA_API_KEY" in text or "SPEECH_PROVIDER" in text:
            offenders.append(str(path.relative_to(REPO)))

    assert offenders == [], f"provider configuration leaked into Go: {offenders}"


def test_the_stt_contract_field_names_are_unchanged():
    """`probability`, not `confidence`.

    A driver that used the other name sent every word through as 0.0 and the
    Pronunciation agent was handed "mean confidence 0.00" for an intelligible
    speaker. The name is part of the contract, so a new provider must translate
    to it rather than introduce its own.
    """
    body = Transcription(
        transcript="hello",
        duration_s=1.0,
        words=[Word(word="hello", start=0.0, end=0.5, probability=0.9)],
    ).to_dict()

    assert "transcript" in body
    assert "duration_s" in body
    assert body["words"][0]["probability"] == 0.9
    assert "confidence" not in body["words"][0]


# --- selection is configured, and recorded ----------------------------------


def test_the_default_provider_is_local(monkeypatch):
    """Gladia costs money per minute and sends candidate audio to a third
    party. Neither is a state to enter by forgetting to set a variable."""
    monkeypatch.delenv("SPEECH_PROVIDER", raising=False)
    assert configured_provider_name() == "faster-whisper"


@pytest.mark.parametrize("value", ["gladia", "GLADIA", " Gladia "])
def test_provider_selection_reads_configuration(monkeypatch, value):
    monkeypatch.setenv("SPEECH_PROVIDER", value)
    assert configured_provider_name() == "gladia"


def test_an_unknown_provider_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "not-a-provider")
    provider = build_provider(whisper_model=object(), whisper_size="base")
    assert isinstance(provider, FasterWhisperProvider)


def test_a_misconfigured_experiment_does_not_take_the_sidecar_down(monkeypatch):
    """An optional experiment must not be able to cause an outage."""
    monkeypatch.setenv("SPEECH_PROVIDER", "gladia")
    monkeypatch.delenv("GLADIA_API_KEY", raising=False)
    monkeypatch.setenv("SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS", "false")

    provider = build_provider(whisper_model=object(), whisper_size="base")
    assert provider is not None


def test_the_response_records_which_provider_produced_it():
    body = Transcription(
        transcript="x", duration_s=2.0, provider="gladia",
        provider_model="gladia-v2", provider_latency_ms=1200,
        estimated_cost_usd=0.00034,
    ).to_dict()

    provenance = body["provenance"]
    assert provenance["provider"] == "gladia"
    assert provenance["model"] == "gladia-v2"
    assert provenance["latency_ms"] == 1200
    assert provenance["estimated_cost_usd"] == 0.00034


def test_an_unpriced_provider_reports_null_not_zero():
    """"We could not price this" and "this was free" are different facts."""
    body = Transcription(transcript="x", duration_s=1.0, estimated_cost_usd=None).to_dict()
    assert body["provenance"]["estimated_cost_usd"] is None

    local = Transcription(
        transcript="x", duration_s=1.0, provider="faster-whisper", estimated_cost_usd=0.0
    ).to_dict()
    assert local["provenance"]["estimated_cost_usd"] == 0.0


# --- normalisation of a real provider response ------------------------------


CASSETTES = REPO / "evals" / "providers" / "cassettes"


def a_cassette() -> dict:
    files = sorted(CASSETTES.glob("*.json"))
    if not files:
        pytest.skip("no recorded provider response available")
    return json.loads(files[0].read_text(encoding="utf-8"))["raw"]


def test_a_recorded_gladia_response_normalises_to_the_sidecar_shape():
    body = normalise_gladia(a_cassette(), latency_ms=8500).to_dict()

    assert body["transcript"]
    assert body["duration_s"] > 0
    assert body["words"], "no word timings survived normalisation"
    assert body["provenance"]["provider"] == "gladia"

    first = body["words"][0]
    assert {"word", "start", "end", "probability"} <= set(first)
    assert first["end"] >= first["start"]


def test_gladia_confidence_is_translated_to_probability():
    """Gladia says `confidence`; the sidecar contract says `probability`.
    Translated at the boundary, which is the only place that knows both names.
    """
    raw = {
        "result": {
            "metadata": {"audio_duration": 2.0},
            "transcription": {
                "full_transcript": "hello there",
                "utterances": [
                    {
                        "start": 0.0, "end": 2.0, "text": "hello there",
                        "words": [{"word": "hello", "start": 0.0, "end": 0.4, "confidence": 0.91}],
                    }
                ],
            },
        }
    }

    body = normalise_gladia(raw).to_dict()
    assert body["words"][0]["probability"] == 0.91


def test_cost_is_derived_from_duration():
    raw = {"result": {"metadata": {"audio_duration": 3600.0},
                      "transcription": {"full_transcript": "x", "utterances": []}}}
    body = normalise_gladia(raw).to_dict()
    # One hour at the configured rate.
    assert body["provenance"]["estimated_cost_usd"] == pytest.approx(
        float(os.getenv("GLADIA_USD_PER_HOUR", "0.612")), rel=1e-3
    )


# --- the comparison -----------------------------------------------------------


def test_wer_is_undefined_against_an_empty_reference():
    """None, not 0.0 or 1.0 -- both constants would be read as a measurement."""
    assert word_error_rate("", "anything") is None
    assert word_error_rate("a b c", "a b c") == 0.0


def test_wer_counts_substitutions_insertions_and_deletions():
    assert word_error_rate("the cat sat", "the dog sat") == pytest.approx(1 / 3, rel=1e-3)
    assert word_error_rate("the cat sat", "the cat") == pytest.approx(1 / 3, rel=1e-3)


def test_fillers_are_counted_including_multi_word_ones():
    counts = count_fillers("Um, I mean, you know, it was, uh, sort of fine.")
    assert counts.get("um") == 1
    assert counts.get("uh") == 1
    assert counts.get("i mean") == 1
    assert counts.get("you know") == 1
    assert counts.get("sort of") == 1


def test_a_tidier_transcript_is_flagged_not_praised():
    """The metric most likely to differ and least likely to be looked at.

    A provider that removes hesitation makes a hesitant candidate read as
    fluent: the transcript improves and the assessment gets worse.
    """
    incumbent = {"transcript": "um so I uh went to the you know shop", "words": [], "duration_s": 5.0}
    challenger = {"transcript": "So I went to the shop", "words": [], "duration_s": 5.0}

    result = compare_transcriptions("item-1", incumbent, challenger)

    assert result.fillers_a > result.fillers_b
    assert result.filler_retention < 0.5
    assert any("hesitation" in note for note in result.notes)


def test_a_band_change_is_called_out_as_the_deciding_measurement():
    result = compare_transcriptions(
        "item-1",
        {"transcript": "a b c", "words": [], "duration_s": 1.0},
        {"transcript": "a b c", "words": [], "duration_s": 1.0},
        band_a=7.0,
        band_b=6.0,
    )

    assert result.band_delta == -1.0
    assert any("only measurement here that decides" in n for n in result.notes)


def test_timing_drift_is_measured():
    incumbent = {
        "transcript": "a b", "duration_s": 2.0,
        "words": [{"word": "a", "start": 0.0, "end": 0.5}, {"word": "b", "start": 1.0, "end": 1.5}],
    }
    challenger = {
        "transcript": "a b", "duration_s": 2.0,
        "words": [{"word": "a", "start": 0.3, "end": 0.8}, {"word": "b", "start": 1.4, "end": 1.9}],
    }

    result = compare_transcriptions("item-1", incumbent, challenger)

    assert result.timing.mean_abs_start_delta_s == pytest.approx(0.35, rel=1e-2)
    assert result.timing.max_abs_start_delta_s == pytest.approx(0.4, rel=1e-2)


def test_the_report_offers_no_recommendation():
    """A field called "recommendation" gets read as the answer. Choosing a
    provider is a human decision on evidence, which is what the report is."""
    report = ComparisonReport(incumbent="faster-whisper", challenger="gladia")
    report.items.append(
        compare_transcriptions(
            "i1",
            {"transcript": "a b c", "words": [], "duration_s": 1.0},
            {"transcript": "a b c", "words": [], "duration_s": 1.0},
        )
    )

    summary = report.summary()
    assert summary["verdict"] == "for human review"
    assert "recommendation" not in summary


def test_the_comparison_cannot_mutate_the_dataset():
    """A comparison able to rewrite a human label could make either provider
    look correct."""
    incumbent = {"transcript": "a b c", "words": [], "duration_s": 1.0}
    challenger = {"transcript": "a b d", "words": [], "duration_s": 1.0}
    before = (json.dumps(incumbent, sort_keys=True), json.dumps(challenger, sort_keys=True))

    compare_transcriptions("i1", incumbent, challenger, band_a=7.0, band_b=6.5)

    after = (json.dumps(incumbent, sort_keys=True), json.dumps(challenger, sort_keys=True))
    assert before == after


def test_the_manifest_is_not_writable_by_the_comparison():
    manifest = REPO / "evals" / "speaking" / "manifest" / "manifest.json"
    source = (REPO / "evals" / "speaking" / "provider_comparison.py").read_text(encoding="utf-8")

    assert manifest.exists()
    # The module opens nothing for writing except the report it is asked to save.
    assert "manifest" not in source.lower()
    assert source.count("write_text") == 1

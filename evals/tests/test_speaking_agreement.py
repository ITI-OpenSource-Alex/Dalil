"""SPEAK-EVAL-007: lane eligibility, reconciliation, and agreement metrics.

The acceptance criteria under test:

  - requesting speaking cannot return `null` or skip while the job passes;
  - lane differences appear in the report;
  - failures remain failures, not numeric bands;
  - all item counts reconcile.

The statistics are checked against hand-computed values rather than against
themselves, because a metric module that agrees with its own implementation is
the one failure mode no amount of test volume catches.
"""

from __future__ import annotations

import pytest

from evals.speaking.agreement import (
    HALF_BAND,
    compute_agreement,
    paired_bootstrap_difference,
)
from evals.speaking.lanes import (
    LANE_SPECS,
    ItemResult,
    Lane,
    Outcome,
    lanes_for,
    reconcile,
)


# --- lane eligibility -------------------------------------------------------


def test_a_transcript_only_item_feeds_the_scorer_lane_and_nothing_else():
    """The IELTS official samples: examiner-banded, but no recording.

    Usable for measuring the scorer against a human label; useless for the audio
    path, because there is no audio to send.
    """
    item = {"inputs": ["transcript"]}
    assert lanes_for(item) == [Lane.SCORER_ONLY]


def test_an_audio_only_item_cannot_feed_the_scorer_lane():
    item = {"inputs": ["audio"]}
    lanes = lanes_for(item)

    assert Lane.SCORER_ONLY not in lanes
    assert set(lanes) == {Lane.GOA_AUDIO, Lane.PRACTICE_E2E, Lane.EXAM}


def test_an_item_with_both_feeds_every_lane():
    assert set(lanes_for({"inputs": ["audio", "transcript"]})) == set(Lane)


def test_an_item_declaring_nothing_feeds_nothing():
    assert lanes_for({}) == []
    assert lanes_for({"inputs": []}) == []


def test_every_lane_records_what_it_exercises():
    """A number has to say what it covers. The scorer lane never touches the
    transport, and a reader must be able to see that without reading the code."""
    for lane, spec in LANE_SPECS.items():
        assert spec.exercises, f"{lane} does not say what it exercises"
        assert spec.requires, f"{lane} does not say what it needs"

    scorer = LANE_SPECS[Lane.SCORER_ONLY].exercises
    assert "stt" not in scorer
    assert "websocket" not in scorer
    assert "prosody" not in scorer

    # The practice lane is the only one that covers the transport that
    # SPEAK-EVAL-002 found broken.
    assert "websocket" in LANE_SPECS[Lane.PRACTICE_E2E].exercises
    assert "audio_format" in LANE_SPECS[Lane.PRACTICE_E2E].exercises


# --- reconciliation ---------------------------------------------------------


def _result(item_id, outcome, predicted=None, reference=None, reason=None):
    return ItemResult(
        item_id=item_id,
        lane=Lane.SCORER_ONLY,
        outcome=outcome,
        predicted_overall=predicted,
        reference_overall=reference,
        reason=reason,
    )


def test_a_failure_carrying_a_band_is_rejected():
    """The defect this project keeps meeting, at the reporting layer."""
    results = [_result("a", Outcome.FAILED, predicted=0.0, reason="provider error")]

    problems = reconcile(results, expected_total=1)

    assert any("a failure must stay a failure" in p for p in problems)


def test_a_not_run_item_must_say_why():
    results = [_result("a", Outcome.NOT_RUN)]
    assert any("no reason recorded" in p for p in reconcile(results, 1))

    results = [_result("a", Outcome.NOT_RUN, reason="lane needs audio; item has none")]
    assert reconcile(results, 1) == []


def test_a_missing_item_is_caught():
    """If an item vanishes between the manifest and the report, the accuracy
    figure has an unknown denominator."""
    results = [_result("a", Outcome.COMPLETE, 6.5, 6.5)]

    problems = reconcile(results, expected_total=3)

    assert any("unaccounted for" in p for p in problems)


def test_not_run_is_not_a_failure():
    """An item the lane could never accept is not a broken pipeline. Collapsing
    the two would make a dataset with no audio look like an outage."""
    not_run = _result("a", Outcome.NOT_RUN, reason="no audio")
    failed = _result("b", Outcome.FAILED, reason="provider 500")

    assert not not_run.scored
    assert not failed.scored
    assert reconcile([not_run, failed], 2) == []


def test_an_item_with_no_reference_does_not_count_as_scored():
    """A prediction with nothing to compare it to is not a data point."""
    assert not _result("a", Outcome.COMPLETE, predicted=6.5).scored
    assert not _result("b", Outcome.COMPLETE, reference=6.5).scored
    assert _result("c", Outcome.COMPLETE, 6.5, 7.0).scored


# --- agreement metrics ------------------------------------------------------


def test_an_empty_comparison_reports_nothing_not_zero():
    """Zero MAE over an empty set is indistinguishable from perfect agreement,
    which makes it the most dangerous number this module could return."""
    metrics = compute_agreement([], [])

    assert metrics.n == 0
    assert metrics.mae is None
    assert metrics.exact_agreement is None
    assert "nothing was measured" in metrics.caveat


def test_mismatched_lengths_are_an_error_not_a_truncation():
    with pytest.raises(ValueError, match="pairing is broken"):
        compute_agreement([6.5, 7.0], [6.5])


def test_perfect_agreement():
    metrics = compute_agreement([6.5, 7.0, 5.5], [6.5, 7.0, 5.5])

    assert metrics.exact_agreement == 1.0
    assert metrics.within_half_band == 1.0
    assert metrics.mae == 0.0
    assert metrics.bias == 0.0
    assert metrics.overscore_rate == 0.0
    assert metrics.underscore_rate == 0.0


def test_metrics_are_hand_checkable():
    """Errors: +0.5, -1.0, 0.0, +0.5. Computed by hand, not by this module."""
    predicted = [7.0, 5.0, 6.5, 7.5]
    reference = [6.5, 6.0, 6.5, 7.0]

    metrics = compute_agreement(predicted, reference)

    assert metrics.n == 4
    assert metrics.exact_agreement == 0.25              # one of four
    assert metrics.within_half_band == 0.75             # three of four
    assert metrics.within_one_band == 1.0
    assert metrics.mae == 0.5                           # (0.5+1.0+0+0.5)/4
    assert metrics.bias == 0.0                          # (+0.5-1.0+0+0.5)/4
    assert metrics.overscore_rate == 0.5
    assert metrics.underscore_rate == 0.25


def test_bias_separates_a_systematic_offset_from_random_error():
    """A uniformly generous system is recalibrated by subtraction; a randomly
    wrong one is not. MAE alone cannot tell them apart."""
    generous = compute_agreement([7.0, 7.5, 6.5], [6.5, 7.0, 6.0])
    scattered = compute_agreement([7.0, 6.5, 6.5], [6.5, 7.0, 6.0])

    assert generous.mae == scattered.mae == 0.5
    assert generous.bias == 0.5
    assert scattered.bias == pytest.approx(0.1667, abs=0.001)


def test_large_errors_are_reported_separately():
    metrics = compute_agreement([9.0, 5.0, 6.5], [6.5, 6.0, 6.5])

    assert metrics.overscore_by_more_than_one == pytest.approx(1 / 3, abs=1e-3)
    assert metrics.underscore_by_more_than_one == 0.0


def test_small_samples_carry_a_caveat_and_an_interval():
    """n=12 is the realistic size of the official IELTS sample set."""
    predicted = [5.0, 5.5, 6.0, 6.0, 6.5, 7.0, 7.0, 7.5, 8.0, 8.0, 8.5, 9.0]
    reference = [5.0, 5.0, 6.0, 6.0, 6.5, 7.0, 7.0, 7.5, 8.0, 8.0, 8.5, 9.0]

    metrics = compute_agreement(predicted, reference)

    assert metrics.n == 12
    assert metrics.caveat is None or "n=12" in metrics.caveat
    assert metrics.mae_ci95 is not None
    assert metrics.mae_ci95.low <= metrics.mae <= metrics.mae_ci95.high
    assert metrics.within_half_band_ci95 is not None


def test_a_tiny_sample_says_so():
    metrics = compute_agreement([6.5, 7.0], [6.5, 6.5])

    assert "n=2" in metrics.caveat
    assert "not a validation" in metrics.caveat


def test_intervals_are_reproducible():
    """A confidence interval that moves every run cannot be compared with the
    last run, which is the main thing anyone wants to do with it."""
    args = ([7.0, 5.0, 6.5, 7.5, 6.0], [6.5, 6.0, 6.5, 7.0, 6.5])

    first = compute_agreement(*args, bootstrap_samples=2000)
    second = compute_agreement(*args, bootstrap_samples=2000)

    assert first.mae_ci95.low == second.mae_ci95.low
    assert first.mae_ci95.high == second.mae_ci95.high


def test_quadratic_weighted_kappa_punishes_distance():
    """Being three bands out must cost more than being one out, which plain
    accuracy does not capture."""
    close = compute_agreement([6.5, 7.0, 5.5, 8.0], [6.0, 7.5, 5.0, 8.5])
    far = compute_agreement([9.0, 5.0, 8.5, 5.0], [6.0, 7.5, 5.0, 8.5])

    assert close.quadratic_weighted_kappa > far.quadratic_weighted_kappa


def test_kappa_is_undefined_when_every_band_is_the_same():
    """Undefined rather than perfect: there is no variation to explain."""
    metrics = compute_agreement([6.5, 6.5, 6.5], [6.5, 6.5, 6.5])
    assert metrics.quadratic_weighted_kappa is None


def test_spearman_ignores_a_uniform_offset():
    """Which is exactly why it is a secondary measure: a system a full band
    generous throughout ranks perfectly and is still unusable."""
    metrics = compute_agreement([7.5, 7.0, 6.5, 6.0], [6.5, 6.0, 5.5, 5.0])

    assert metrics.spearman == 1.0
    assert metrics.mae == 1.0
    assert metrics.bias == 1.0


def test_the_confusion_matrix_is_keyed_reference_then_predicted():
    metrics = compute_agreement([7.0, 7.0, 6.0], [6.5, 6.5, 6.0])

    assert metrics.confusion["6.5"]["7.0"] == 2
    assert metrics.confusion["6.0"]["6.0"] == 1


# --- paired comparison ------------------------------------------------------


def test_a_paired_comparison_reports_when_it_cannot_distinguish():
    """An interval spanning zero is a finding, not something to resolve by
    picking the smaller point estimate."""
    candidate = [0.5, -0.5, 0.5, -0.5]
    baseline = [0.5, -0.5, 0.5, -0.5]

    outcome = paired_bootstrap_difference(candidate, baseline, bootstrap_samples=2000)

    assert outcome["mae_difference"] == 0.0
    assert outcome["conclusive"] is False


def test_a_clear_improvement_is_conclusive():
    candidate = [0.0] * 12
    baseline = [1.5] * 12

    outcome = paired_bootstrap_difference(candidate, baseline, bootstrap_samples=2000)

    assert outcome["mae_difference"] == -1.5
    assert outcome["conclusive"] is True


def test_a_paired_comparison_needs_the_same_items():
    with pytest.raises(ValueError, match="same items"):
        paired_bootstrap_difference([0.5], [0.5, 0.5])


def test_half_band_is_the_tolerance_of_the_scale():
    """Not an arbitrary epsilon: IELTS moves in half steps, so one step is the
    natural unit of 'close enough'."""
    assert HALF_BAND == 0.5

    metrics = compute_agreement([7.0], [6.5])
    assert metrics.within_half_band == 1.0
    assert metrics.exact_agreement == 0.0


# --- the promotion path -----------------------------------------------------


def test_promoting_the_official_samples_opens_only_the_scorer_lane():
    """The end-to-end governance property, exercised on the real manifest.

    The 12 official IELTS samples carry examiner bands but no audio. Once
    somebody reviews the terms and promotes them, the scorer lane must become
    runnable and the three audio lanes must stay shut -- because there is still
    no recording. If a promotion could open an audio lane, the report could
    claim the audio path was validated on transcript-only evidence.
    """
    import copy
    import json
    from pathlib import Path

    from evals.speaking.lanes import eligible_items
    from evals.speaking.manifest import validate as manifest_validate

    repo = Path(__file__).resolve().parents[2]
    manifest_dir = repo / "evals" / "speaking" / "manifest"
    manifest = json.loads((manifest_dir / "manifest.json").read_text(encoding="utf-8"))

    official = [i for i in manifest["items"] if i["item_id"].startswith("ielts-official-")]
    assert len(official) == 12, "the official sample set should be all 12 published items"

    # As shipped: unreviewed, therefore ungated.
    for item in official:
        assert item["permission"]["status"] == "pending"
        assert item["labels"]["source"] == "official"
        assert item["labels"]["validated"] is True
        assert item["labels"]["overall_band"] is not None
        # No per-criterion labels exist; the examiners publish one number.
        assert "criteria" not in item["labels"]
    assert manifest_validate.gating_items(manifest) == []

    promoted = copy.deepcopy(manifest)
    for item in promoted["items"]:
        if item["item_id"].startswith("ielts-official-"):
            item["split"] = "smoke"
            item["permission"].update({
                "status": "granted",
                "reviewed_by": "a-named-person",
                "reviewed_at": "2026-08-09T00:00:00+00:00",
            })
            item["transcript"].update({"sha256": "b" * 64})

    problems = manifest_validate.validate(
        promoted, root=manifest_dir, sweep_root=manifest_validate.SPEAKING_ROOT
    )
    assert problems == [], "\n".join(str(p) for p in problems)

    assert len(eligible_items(promoted, Lane.SCORER_ONLY)) == 12
    for audio_lane in (Lane.GOA_AUDIO, Lane.PRACTICE_E2E, Lane.EXAM):
        assert eligible_items(promoted, audio_lane) == []


def test_a_promoted_transcript_item_still_needs_its_hash():
    """A reference text that can change silently is not a reference."""
    import copy
    import json
    from pathlib import Path

    from evals.speaking.manifest import validate as manifest_validate

    repo = Path(__file__).resolve().parents[2]
    manifest_dir = repo / "evals" / "speaking" / "manifest"
    manifest = json.loads((manifest_dir / "manifest.json").read_text(encoding="utf-8"))

    promoted = copy.deepcopy(manifest)
    for item in promoted["items"]:
        if item["item_id"].startswith("ielts-official-"):
            item["split"] = "smoke"
            item["permission"].update({
                "status": "granted",
                "reviewed_by": "someone",
                "reviewed_at": "2026-08-09T00:00:00+00:00",
            })
            # transcript.sha256 deliberately left absent

    problems = manifest_validate.check_gating_eligibility(promoted)
    assert any("no integrity hash" in str(p) for p in problems)


def test_the_speaking_eval_never_returns_a_bare_null():
    """Acceptance: requesting speaking cannot return null or skip while the job
    passes. It may decline to produce a number; it may not decline to say why."""
    from evals.runner import run_speaking_eval

    result = run_speaking_eval({})

    assert "speaking_lanes" in result
    assert set(result["speaking_lanes"]) == {lane.value for lane in Lane}
    assert result["speaking_reason"]
    for name, entry in result["speaking_lanes"].items():
        assert entry["reason"], f"{name} reports no reason"
        assert entry["state"] in {"not_run", "pending_runner", "complete"}
        assert entry["exercises"], f"{name} does not say what it covers"


def test_the_scorer_lane_can_never_claim_the_pipeline_was_exercised():
    """Transcript-only evidence must not set speaking_pipeline_exercised."""
    from evals.runner import run_speaking_eval

    result = run_speaking_eval({})
    assert result["speaking_pipeline_exercised"] is False

"""SPEAK-EVAL-004 — the speaking dataset manifest must be binding, not descriptive.

The committed manifest passing its own validators proves very little: a validator
that never fires passes everything. So each test here constructs a manifest that
violates exactly one rule and asserts that rule catches it, then asserts the real
manifest is clean.

The rules under test map one-to-one onto the ticket's acceptance criteria:

  1. invalid/unlicensed/unvalidated items cannot enter a gating split
  2. candidates and source series cannot cross splits
  3. every approved source has an integrity hash and governance reference
  4. no restricted audio is committed accidentally
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO / "evals" / "speaking" / "manifest"
sys.path.insert(0, str(MANIFEST_DIR))

import validate as manifest_validate  # noqa: E402


HASH = "a" * 64


@pytest.fixture
def real_manifest() -> dict:
    return manifest_validate.load_manifest(MANIFEST_DIR / "manifest.json")


def _permitted_item(item_id: str, split: str, **overrides) -> dict:
    """A fully compliant gating item, for tests to break one field of."""
    item = {
        "item_id": item_id,
        "candidate_id": f"cand-{item_id}",
        "series_id": f"series-{item_id}",
        "split": split,
        # What the item provides. Gating keys off this rather than off a blanket
        # audio requirement -- see the note in check_gating_eligibility.
        "inputs": ["audio"],
        "source": {
            "kind": "public_recording",
            "origin_url": "https://example.org/ielts-speaking-band-7",
            "governance_ref": "SPEAK-EVAL-004",
        },
        "permission": {
            "status": "granted",
            "basis": "Written permission from the publisher.",
            "governance_ref": "SPEAK-EVAL-004",
            "reviewed_by": "a-named-person",
        },
        "media": {
            "storage": "external",
            "restricted": False,
            "sha256": HASH,
            "duration_s": 120.0,
        },
        "labels": {
            "source": "official",
            "validated": True,
            "overall_band": 7.0,
        },
        "retention": {"policy": "indefinite"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(item.get(key), dict):
            item[key] = {**item[key], **value}
        else:
            item[key] = value
    return item


def _manifest_with(*items: dict) -> dict:
    return {
        "manifest_version": "speaking-dataset-manifest/v1",
        "splits": {
            "quarantine": {"gating": False, "purpose": "test"},
            "smoke": {"gating": True, "purpose": "test"},
            "test": {"gating": True, "purpose": "test"},
        },
        "items": list(items),
    }


def _rules(problems) -> set[str]:
    return {p.rule for p in problems}


# --- the committed manifest -------------------------------------------------


def test_the_committed_manifest_is_clean(real_manifest):
    problems = manifest_validate.validate(real_manifest, root=MANIFEST_DIR)
    assert problems == [], "\n".join(str(p) for p in problems)


def test_the_synthetic_items_are_quarantined_and_cannot_gate(real_manifest):
    """The ticket's fifth behaviour task, asserted rather than asserted-to.

    These 20 rows are model-written transcripts with model-assigned bands. They
    are useful for exercising the plumbing and worthless as an accuracy claim,
    and the difference has to be enforced somewhere other than a comment.
    """
    assert manifest_validate.gating_items(real_manifest) == []

    # The 20 golden-dataset rows specifically: model-written transcripts with
    # model-assigned bands. Selected on the label source rather than on
    # `source.kind`, because the pipeline fixture is synthetic too and would
    # otherwise be counted here -- it is a different kind of unusable.
    model_banded = [
        item
        for item in real_manifest["items"]
        if item["labels"]["source"] == "model_generated"
    ]
    assert len(model_banded) == 20

    for item in model_banded:
        assert item["split"] == "quarantine"
        assert item["labels"]["validated"] is False

    # And nothing synthetic, of either kind, is anywhere near a gating split.
    for item in real_manifest["items"]:
        if item["source"]["kind"] == "synthetic":
            assert item["split"] == "quarantine"
            assert item["labels"]["validated"] is False


def test_promoting_a_synthetic_item_to_a_gating_split_is_rejected(real_manifest):
    """The quarantine has to survive somebody deciding to move an item."""
    tampered = copy.deepcopy(real_manifest)
    tampered["items"][0]["split"] = "smoke"

    problems = manifest_validate.validate(tampered, root=MANIFEST_DIR)
    assert "gating" in _rules(problems)

    messages = " ".join(str(p) for p in problems)
    assert "never validated by a human" in messages
    assert "agreement with a" in messages


# --- rule 1: gating eligibility ---------------------------------------------


@pytest.mark.parametrize(
    "overrides, expected_fragment",
    [
        ({"permission": {"status": "pending"}}, "permission status"),
        ({"permission": {"status": "unknown"}}, "permission status"),
        ({"permission": {"status": "denied"}}, "permission status"),
        ({"labels": {"validated": False}}, "never validated by a human"),
        ({"labels": {"source": "model_generated"}}, "agreement with a"),
        ({"labels": {"source": "none"}}, "agreement with a"),
        ({"labels": {"overall_band": None}}, "no band"),
        ({"media": {"storage": "none"}}, "declares audio input but stores no media"),
        ({"media": {"sha256": None}}, "no integrity hash"),
    ],
)
def test_an_ineligible_item_cannot_sit_in_a_gating_split(overrides, expected_fragment):
    manifest = _manifest_with(_permitted_item("x-01", "smoke", **overrides))

    problems = manifest_validate.check_gating_eligibility(manifest)

    assert problems, f"expected {overrides} to be rejected from a gating split"
    assert expected_fragment in " ".join(str(p) for p in problems)


def test_the_same_defects_are_tolerated_outside_a_gating_split():
    """Quarantine exists precisely so imperfect items can be kept, not deleted."""
    manifest = _manifest_with(
        _permitted_item(
            "x-01",
            "quarantine",
            permission={"status": "unknown"},
            labels={"source": "model_generated", "validated": False, "overall_band": None},
            media={"storage": "none", "sha256": None},
        )
    )
    assert manifest_validate.check_gating_eligibility(manifest) == []


def test_double_rating_must_name_two_raters():
    manifest = _manifest_with(
        _permitted_item(
            "x-01",
            "smoke",
            labels={
                "source": "commissioned_double_rated",
                "validated": True,
                "overall_band": 6.5,
                "raters": ["only-one-person"],
            },
        )
    )
    problems = manifest_validate.check_gating_eligibility(manifest)
    assert "names 1 rater" in " ".join(str(p) for p in problems)


def test_an_undeclared_split_is_rejected():
    manifest = _manifest_with(_permitted_item("x-01", "a-split-nobody-declared"))
    problems = manifest_validate.check_gating_eligibility(manifest)
    assert "is not declared" in " ".join(str(p) for p in problems)


# --- rule 2: split leakage --------------------------------------------------


def test_a_candidate_cannot_appear_in_two_splits():
    manifest = _manifest_with(
        _permitted_item("x-01", "smoke", candidate_id="same-person"),
        _permitted_item("x-02", "test", candidate_id="same-person"),
    )
    problems = manifest_validate.check_split_leakage(manifest)
    assert len(problems) == 1
    assert "candidate_id 'same-person'" in str(problems[0])


def test_a_series_cannot_appear_in_two_splits():
    """The quieter of the two leaks.

    One recording shares an examiner, a microphone and an editing pass. Splitting
    it across a comparison leaks the conditions even when every speaker differs.
    """
    manifest = _manifest_with(
        _permitted_item("x-01", "smoke", series_id="one-youtube-video"),
        _permitted_item("x-02", "test", series_id="one-youtube-video"),
    )
    problems = manifest_validate.check_split_leakage(manifest)
    assert len(problems) == 1
    assert "series_id 'one-youtube-video'" in str(problems[0])


def test_many_items_from_one_series_in_one_split_are_fine():
    manifest = _manifest_with(
        _permitted_item("x-01", "smoke", series_id="one-video", candidate_id="a"),
        _permitted_item("x-02", "smoke", series_id="one-video", candidate_id="b"),
        _permitted_item("x-03", "smoke", series_id="one-video", candidate_id="c"),
    )
    assert manifest_validate.check_split_leakage(manifest) == []


# --- rule 3: governance records ---------------------------------------------


@pytest.mark.parametrize(
    "permission_overrides, expected_fragment",
    [
        ({"basis": None}, "no stated basis"),
        ({"governance_ref": None}, "no governance reference"),
        ({"reviewed_by": None}, "nobody is recorded as having reviewed it"),
    ],
)
def test_an_approved_source_must_record_its_approval(permission_overrides, expected_fragment):
    item = _permitted_item("x-01", "smoke")
    item["permission"].update(permission_overrides)
    problems = manifest_validate.check_permission_records(_manifest_with(item))
    assert expected_fragment in " ".join(str(p) for p in problems)


def test_media_without_a_hash_is_rejected():
    """A hash is what makes a silent replacement detectable."""
    item = _permitted_item("x-01", "smoke", media={"sha256": None})
    problems = manifest_validate.check_permission_records(_manifest_with(item))
    assert "no integrity hash" in " ".join(str(p) for p in problems)


def test_a_transcript_only_item_needs_no_media_hash():
    item = _permitted_item("x-01", "quarantine", media={"storage": "none", "sha256": None})
    assert manifest_validate.check_permission_records(_manifest_with(item)) == []


# --- rule 4: restricted media -----------------------------------------------


def test_restricted_audio_cannot_be_stored_in_the_repo(tmp_path):
    item = _permitted_item(
        "x-01",
        "smoke",
        media={"storage": "repo", "restricted": True, "path": "evals/speaking/x.wav", "sha256": HASH},
    )
    problems = manifest_validate.check_restricted_media(_manifest_with(item), root=tmp_path)
    assert "marked restricted and stored in the repository" in " ".join(str(p) for p in problems)


def test_repo_media_must_declare_a_path(tmp_path):
    item = _permitted_item(
        "x-01", "smoke", media={"storage": "repo", "restricted": False, "sha256": HASH}
    )
    problems = manifest_validate.check_restricted_media(_manifest_with(item), root=tmp_path)
    assert "no path is given" in " ".join(str(p) for p in problems)


def test_an_undeclared_audio_file_in_the_tree_is_caught(tmp_path):
    """What an accidental `git add` of a downloaded recording actually looks like.

    Checking only the manifest would miss this entirely: the file is on disk and
    the manifest says nothing about it, so there is no entry to find wrong.
    """
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "downloaded-from-youtube.mp3").write_bytes(b"not really audio")

    problems = manifest_validate.check_restricted_media(_manifest_with(), root=tmp_path)

    assert len(problems) == 1
    assert "undeclared audio file" in str(problems[0])
    assert "downloaded-from-youtube.mp3" in str(problems[0])


def test_a_declared_audio_file_is_accepted_and_hash_checked(tmp_path):
    import hashlib

    clips = tmp_path / "clips"
    clips.mkdir()
    audio = clips / "declared.wav"
    payload = b"RIFF....WAVE fake payload"
    audio.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    item = _permitted_item(
        "x-01",
        "smoke",
        media={
            "storage": "repo",
            "restricted": False,
            "path": str(audio),
            "sha256": digest,
        },
    )
    assert manifest_validate.check_restricted_media(_manifest_with(item), root=tmp_path) == []

    # And a byte changing under it must be caught.
    audio.write_bytes(payload + b"tampered")
    problems = manifest_validate.check_restricted_media(_manifest_with(item), root=tmp_path)
    assert "media hash mismatch" in " ".join(str(p) for p in problems)


# --- the schema itself ------------------------------------------------------


def test_the_manifest_matches_its_schema(real_manifest):
    jsonschema = pytest.importorskip("jsonschema")

    with (MANIFEST_DIR / "schema" / "dataset-manifest-v1.schema.json").open(
        encoding="utf-8"
    ) as handle:
        schema = json.load(handle)

    jsonschema.Draft202012Validator(schema).validate(real_manifest)


def test_the_schema_rejects_an_unknown_permission_status():
    jsonschema = pytest.importorskip("jsonschema")

    with (MANIFEST_DIR / "schema" / "dataset-manifest-v1.schema.json").open(
        encoding="utf-8"
    ) as handle:
        schema = json.load(handle)

    manifest = _manifest_with(_permitted_item("x-01", "smoke"))
    manifest["items"][0]["permission"]["status"] = "probably fine"

    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors(manifest)), "an invented status must not validate"

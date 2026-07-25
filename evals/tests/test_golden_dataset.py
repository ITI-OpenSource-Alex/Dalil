import json

import pytest
from pathlib import Path

GOLDEN_PATH = Path(__file__).parent.parent / "golden_dataset.json"

def test_golden_dataset_shape():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    
    # Writing checks
    writing_rows = data.get("writing", [])
    assert len(writing_rows) > 0
    writing_ids = set()
    for row in writing_rows:
        assert "id" in row
        assert "essay" in row
        assert "task_type" in row
        assert row["task_type"] == "task2"
        assert "expected_band" in row
        assert "expected_criteria" in row
        assert "band_source" in row
        # Either a hand-written note or the published examiner comment.
        assert row.get("notes") or row.get("examiner_comment"), (
            f"{row['id']} has no notes and no examiner_comment"
        )
        assert row["id"] not in writing_ids, f"Duplicate writing ID: {row['id']}"
        writing_ids.add(row["id"])

        # Per-criterion bands are OPTIONAL. IELTS publishes only the overall band for
        # its official sample scripts, so demanding four criterion bands would force
        # invented numbers onto the only rows with real provenance — exactly the
        # fabrication this dataset was rebuilt to remove. Rows without them are scored
        # on the overall band, and MAE simply skips the criterion breakdown.
        criteria = row["expected_criteria"]
        if criteria:
            for key in ("task_response", "coherence", "lexical", "grammar"):
                assert key in criteria, f"Missing writing criteria key '{key}' in {row['id']}"
                assert isinstance(criteria[key], (int, float))

    # Speaking checks
    speaking_rows = data.get("speaking", [])
    assert len(speaking_rows) > 0
    speaking_ids = set()
    for row in speaking_rows:
        assert "id" in row
        assert "transcript" in row
        assert "task_type" in row
        assert row["task_type"] == "speaking"
        assert "expected_band" in row
        assert "expected_criteria" in row
        assert "band_source" in row
        assert "notes" in row
        assert row["id"] not in speaking_ids, f"Duplicate speaking ID: {row['id']}"
        speaking_ids.add(row["id"])
        
        criteria = row["expected_criteria"]
        for key in ("fluency_coherence", "lexical_resource", "grammatical_range", "pronunciation"):
            assert key in criteria, f"Missing speaking criteria key '{key}' in {row['id']}"
            assert isinstance(criteria[key], (int, float))

@pytest.mark.xfail(
    reason="Ticket target is 20 validated rows per domain. Only 3 officially "
           "examiner-banded Task 2 scripts are published free (2 Academic, 1 GT). "
           "The remaining 17 must be self-authored and banded by a named person "
           "— see GOA-028 Task 1.",
    strict=False,
)
def test_golden_dataset_size():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert len(data.get("writing", [])) >= 20, "Expected >= 20 writing rows"
    assert len(data.get("speaking", [])) >= 20, "Expected >= 20 speaking rows"

def test_band_distribution_is_spread():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for domain in ("writing", "speaking"):
        rows = data.get(domain, [])
        total = len(rows)
        counts = {}
        for row in rows:
            band = row["expected_band"]
            counts[band] = counts.get(band, 0) + 1
        for band, count in counts.items():
            ratio = count / total
            assert ratio <= 0.40, f"Domain {domain} band {band} constitutes {ratio:.1%} (> 40% threshold)"

def test_no_placeholder_rows():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for domain, text_key in [("writing", "essay"), ("speaking", "transcript")]:
        for row in data.get(domain, []):
            assert "dummy" not in row[text_key].lower(), f"Placeholder 'dummy' in {domain} ID {row['id']}"
            assert "dummy" not in row.get("notes", "").lower(), f"Placeholder 'dummy' in notes of {domain} ID {row['id']}"


# --- Validity guards added after review: the original suite checked that band_source
# --- was PRESENT, not that it meant anything, and never checked essay length at all.
# --- Both gaps let a dataset through that cannot support any accuracy claim.

IELTS_TASK2_MIN_WORDS = 250


def _load():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_under_length_essays_are_recorded_not_assumed_full_length():
    """Under-length answers are legitimate golden data — but must be visible.

    IELTS Task 2 asks for 250+ words and penalises shortfall, yet official sample
    scripts include a 198-word answer banded 5.5 and a 220-word answer banded 5.0: the
    examiner applies the penalty and says so in the comment. So the rule is not "every
    essay must be 250 words"; it is "if an essay is short, that fact must be on the
    record", because an agent that marks it down is behaving CORRECTLY and the golden
    band already accounts for it.
    """
    data = _load()
    for row in data["writing"]:
        words = len(row["essay"].split())
        if words < IELTS_TASK2_MIN_WORDS:
            assert row.get("word_count") == words, (
                f"{row['id']} is {words} words (under the {IELTS_TASK2_MIN_WORDS} "
                f"minimum) but does not record word_count"
            )


def test_band_source_is_provenance_not_a_restatement_of_the_band():
    """'Public IELTS Descriptor Rubric & Expert Benchmark (Band 6.5)' is circular: the
    source for band 6.5 is '(Band 6.5)'. Provenance must name WHO banded it or WHERE it
    came from — or say plainly that it is unvalidated."""
    data = _load()
    offenders = []
    for domain in ("writing", "speaking"):
        for row in data[domain]:
            source = (row.get("band_source") or "").lower()
            band = str(row["expected_band"])
            names_a_source = any(
                marker in source
                for marker in ("ielts.org", "cambridge", "self-authored", "banded by",
                               "synthetic", "examiner")
            )
            # A source whose only specific content is the band it is sourcing.
            circular = band in source and not names_a_source
            if circular or not source:
                offenders.append(row["id"])
    assert not offenders, f"band_source is circular or empty for: {offenders[:8]}"


def test_unvalidated_labels_are_flagged_so_reports_cannot_overclaim():
    """If labels are synthetic, every consumer must be able to see that."""
    data = _load()
    for domain in ("writing", "speaking"):
        for row in data[domain]:
            source = (row.get("band_source") or "").lower()
            if "synthetic" in source:
                assert row.get("label_validated") is False, (
                    f"{row['id']} is synthetic but not flagged label_validated=False"
                )

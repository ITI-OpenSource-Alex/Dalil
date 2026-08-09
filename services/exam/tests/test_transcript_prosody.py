"""GOA-133 — stitching per-part word timings into one timeline.

The three parts are recorded separately, minutes apart, and each part's timings
start at 0. Getting the offsets wrong produces silences the candidate never took,
which land straight in the long-pause count the Fluency agent reads.
"""

import json

import pytest

from app.services.transcript_prosody import BOUNDARY_GAP_S, merge_part_timings


def part(number, words, audio_duration_s=None, duration_s=0):
    return {
        "part": number,
        "words": words,
        "audio_duration_s": audio_duration_s,
        "duration_s": duration_s,
    }


def w(word, start, end, probability=0.9):
    return {"word": word, "start": start, "end": end, "probability": probability}


def test_single_part_is_unchanged():
    merged, duration = merge_part_timings([
        part(1, [w("a", 0.0, 0.5), w("b", 1.0, 1.5)], audio_duration_s=10.0),
    ])
    assert [m["start"] for m in merged] == [0.0, 1.0]
    assert duration == 10.0


def test_later_parts_are_offset_by_cumulative_audio_duration():
    merged, duration = merge_part_timings([
        part(1, [w("a", 0.0, 0.5)], audio_duration_s=10.0),
        part(2, [w("b", 0.0, 0.5)], audio_duration_s=20.0),
        part(3, [w("c", 0.0, 0.5)], audio_duration_s=5.0),
    ])
    starts = [m["start"] for m in merged]
    assert starts[0] == 0.0
    assert starts[1] == pytest.approx(10.0 + BOUNDARY_GAP_S)
    assert starts[2] == pytest.approx(30.0 + 2 * BOUNDARY_GAP_S)
    assert duration == pytest.approx(35.0, abs=0.2)


def test_part_boundary_is_not_a_hesitation():
    """The gap across a recording boundary must stay below the speaking service's
    0.3s pause threshold, or every session gains two pauses nobody took."""
    merged, _ = merge_part_timings([
        part(1, [w("a", 0.0, 5.0)], audio_duration_s=5.0),
        part(2, [w("b", 0.0, 5.0)], audio_duration_s=5.0),
    ])
    gap = merged[1]["start"] - merged[0]["end"]
    assert gap < 0.3, f"boundary gap of {gap}s would register as a pause"


def test_words_never_land_before_the_preceding_part():
    """A sidecar duration and a session clock can disagree. When the words run
    past the declared duration, the next part must still start after them."""
    merged, _ = merge_part_timings([
        part(1, [w("a", 0.0, 12.0)], audio_duration_s=5.0),  # words exceed duration
        part(2, [w("b", 0.0, 1.0)], audio_duration_s=5.0),
    ])
    assert merged[1]["start"] > merged[0]["end"]


def test_missing_timings_still_consume_their_duration():
    """A part without stored words contributes no words but must still advance the
    timeline. Skipping it would compress the session and inflate words-per-minute."""
    merged, duration = merge_part_timings([
        part(1, [w("a", 0.0, 0.5)], audio_duration_s=10.0),
        part(2, None, audio_duration_s=60.0),
        part(3, [w("c", 0.0, 0.5)], audio_duration_s=10.0),
    ])
    assert len(merged) == 2
    assert merged[1]["start"] == pytest.approx(70.0 + 2 * BOUNDARY_GAP_S)
    assert duration == pytest.approx(80.0, abs=0.2)


def test_no_timings_anywhere_returns_empty():
    """The caller must then omit the feature block. Returning a zero duration with
    words would let a zeroed block be rendered -- the BUG-055 shape."""
    merged, duration = merge_part_timings([
        part(1, None, audio_duration_s=10.0),
        part(2, None, audio_duration_s=10.0),
    ])
    assert merged == []
    assert duration == 0.0


def test_falls_back_to_the_session_clock_when_audio_duration_is_absent():
    merged, duration = merge_part_timings([
        part(1, [w("a", 0.0, 0.5)], audio_duration_s=None, duration_s=15),
        part(2, [w("b", 0.0, 0.5)], audio_duration_s=None, duration_s=25),
    ])
    assert merged[1]["start"] == pytest.approx(15.0 + BOUNDARY_GAP_S)
    assert duration == pytest.approx(40.0, abs=0.2)


def test_words_stored_as_a_json_string_are_accepted():
    """asyncpg returns JSONB as a string unless a codec is registered."""
    merged, _ = merge_part_timings([
        part(1, json.dumps([w("a", 0.0, 0.5)]), audio_duration_s=10.0),
    ])
    assert len(merged) == 1
    assert merged[0]["word"] == "a"


def test_malformed_word_entries_are_skipped_not_fatal():
    merged, _ = merge_part_timings([
        part(1, [w("a", 0.0, 0.5), {"word": "b"}, {"start": "x", "end": "y"}], audio_duration_s=10.0),
    ])
    assert len(merged) == 1


def test_probability_is_preserved():
    merged, _ = merge_part_timings([
        part(1, [w("a", 0.0, 0.5, probability=0.42)], audio_duration_s=10.0),
    ])
    assert merged[0]["probability"] == pytest.approx(0.42)

"""GOA-133 — stitch per-part word timings into one continuous timeline.

The three IELTS speaking parts are recorded as separate sessions, minutes apart.
Each part's word timings come back from the speech sidecar relative to *that
part's* audio, starting at 0. The holistic evaluator grades the concatenated
transcript, so it needs one coherent timeline.

Offsetting each part by the CUMULATIVE AUDIO DURATION of the parts before it is
what makes that timeline honest. Offsetting by wall-clock time instead would
insert the minutes between recordings as a silence, and the Fluency agent would
read a five-minute hesitation that never happened.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

# A part boundary is a recording boundary, not a hesitation. Trailing silence at
# the end of one part and leading silence at the start of the next would
# otherwise concatenate into a pause that no candidate took, and that pause lands
# directly in the long-pause count the Fluency agent reads.
#
# The gap across a boundary is clamped to this: short enough never to register as
# a pause (the speaking service's threshold is 0.3s), long enough that words do
# not overlap.
BOUNDARY_GAP_S = 0.05


def _coerce_words(raw: Any) -> list[dict]:
    """asyncpg hands JSONB back as a string unless a codec is registered.

    Accept both shapes rather than assuming one -- the same defensive read
    rag_service._faq_sources needs for the same reason.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    return [w for w in raw if isinstance(w, dict)]


def merge_part_timings(transcripts: Iterable[Any]) -> tuple[list[dict], float]:
    """Return (words on one timeline, total audio duration).

    `transcripts` are the per-part rows in part order. Parts without stored
    timings contribute their duration to the timeline but no words, so a session
    where only some parts carry timings still produces a usable -- if partial --
    picture rather than a wrong one.

    Returns ([], 0.0) when no part carries timings. The caller must then omit the
    feature block entirely; rendering it from a zero duration would describe a
    candidate who said nothing.
    """
    merged: list[dict] = []
    offset = 0.0
    total_duration = 0.0

    for row in transcripts:
        words = _coerce_words(row.get("words") if isinstance(row, dict) else row["words"])

        raw_audio = (
            row.get("audio_duration_s") if isinstance(row, dict) else row["audio_duration_s"]
        )
        if raw_audio is not None:
            part_duration = float(raw_audio)
        else:
            # Fall back to the session clock's integer seconds. Lossy -- it is the
            # reason audio_duration_s exists -- but better than dropping the part
            # from the timeline, which would compress the whole session and
            # inflate words per minute.
            raw_clock = row.get("duration_s") if isinstance(row, dict) else row["duration_s"]
            part_duration = float(raw_clock or 0)

        if words:
            part_end = 0.0
            for word in words:
                try:
                    start = float(word["start"])
                    end = float(word["end"])
                except (KeyError, TypeError, ValueError):
                    # A malformed entry is skipped, not fatal. One bad row in a
                    # sidecar response must not cost the whole session its timings.
                    continue
                part_end = max(part_end, end)
                merged.append({
                    "word": word.get("word", ""),
                    "start": round(offset + start, 3),
                    "end": round(offset + end, 3),
                    "probability": float(word.get("probability", 0.0)),
                })

            # Advance by the part's own extent when it exceeds the declared
            # duration: a sidecar duration and a session clock can disagree, and
            # words must never land before the part that precedes them.
            #
            # Computed from the entries that PARSED, not the raw list -- reading
            # the raw list here raised KeyError on a malformed row and took the
            # whole evaluation down, which is exactly what the skip above exists
            # to prevent.
            part_duration = max(part_duration, part_end)

        total_duration += part_duration
        offset += part_duration + BOUNDARY_GAP_S

    if not merged:
        return [], 0.0

    # Duration is the extent of the timeline the words actually sit on, boundary
    # gaps included. Reporting the sum of part durations instead would be a
    # slightly smaller denominator than the one words-per-minute is computed
    # against, and the two figures would disagree for no reason a reader could see.
    timeline_end = max(float(w["end"]) for w in merged)
    return merged, round(max(total_duration, timeline_end), 3)

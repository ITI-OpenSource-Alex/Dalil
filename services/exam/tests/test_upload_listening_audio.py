from __future__ import annotations

import pytest

from scripts.upload_listening_audio import choose_section_starts


def test_section_transitions_use_position_not_only_longest_silences() -> None:
    duration = 1_858.0
    silences = [
        (72.0, 97.0, 25.0),
        (399.0, 460.0, 61.0),
        (654.0, 685.0, 31.0),
        (848.0, 879.0, 31.0),
        (894.0, 925.0, 31.0),
        (1_111.0, 1_137.0, 26.0),
        (1_328.0, 1_394.0, 66.0),
        (1_785.0, 1_845.0, 60.0),
    ]

    assert choose_section_starts(duration, silences) == [460.0, 925.0, 1_394.0]


def test_section_transition_detection_fails_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="50%"):
        choose_section_starts(
            1_800.0,
            [(400.0, 450.0, 50.0), (1_300.0, 1_350.0, 50.0)],
        )

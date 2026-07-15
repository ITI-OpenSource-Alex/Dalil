from app.services.grading_service import GradingService


def test_grading_service_returns_expected_score() -> None:
    result = GradingService().grade(
        submitted_answers={"answers": {"1": "A", "2": "B", "3": "wrong"}},
        answer_key={"answers": {"1": "a", "2": ["b", "bee"], "3": "c"}},
        skill_area="reading",
    )

    assert result == {
            "raw_score": 2,
            "band_score": 6.5,
            "section_scores": {"overall": {"correct": 2, "total": 3}},
        }

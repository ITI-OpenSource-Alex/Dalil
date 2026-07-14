from app.services.grading_service import GradingService


def _build_answer_key(count: int = 40) -> dict[str, str]:
    answers = {}
    for i in range(1, count + 1):
        answers[str(i)] = f"ANSWER{i}"
    return answers


class TestFillBlankNormalization:
    def test_case_insensitive_match(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "true", "2": "False", "3": "NOT GIVEN"},
            answer_key={"1": "TRUE", "2": "FALSE", "3": "NOT GIVEN"},
        )
        assert result["raw_score"] == 3
        for q in ["1", "2", "3"]:
            assert result["per_question_result"][q]["is_correct"] is True

    def test_whitespace_trimming(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "  hello  ", "2": "world"},
            answer_key={"1": "hello", "2": "world"},
        )
        assert result["raw_score"] == 2

    def test_internal_double_spaces(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "ice  cream"},
            answer_key={"1": "ice cream"},
        )
        assert result["raw_score"] == 1
        assert result["per_question_result"]["1"]["is_correct"] is True

    def test_wrong_answer_marked_incorrect(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "TRUE", "2": "WRONG"},
            answer_key={"1": "TRUE", "2": "FALSE"},
        )
        assert result["raw_score"] == 1
        assert result["per_question_result"]["1"]["is_correct"] is True
        assert result["per_question_result"]["2"]["is_correct"] is False
        assert result["per_question_result"]["2"]["correct_answer"] == "FALSE"

    def test_missing_answer_is_incorrect(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={},
            answer_key={"1": "A"},
        )
        assert result["raw_score"] == 0
        assert result["per_question_result"]["1"]["is_correct"] is False
        assert result["per_question_result"]["1"]["submitted_answer"] == ""

    def test_multi_answer_accepted(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "COLOUR"},
            answer_key={"1": ["COLOR", "COLOUR"]},
        )
        assert result["raw_score"] == 1


class TestBandConversion:
    def _check_band(
        self, raw: int, exam_type: str, expected: float
    ) -> None:
        gs = GradingService()
        key = {str(i): f"A{i}" for i in range(1, 41)}
        correct = {str(i): f"A{i}" for i in range(1, raw + 1)}
        wrong = {str(i): "WRONG" for i in range(raw + 1, 41)}
        submitted = {**correct, **wrong}
        result = gs.grade_reading(
            submitted_answers=submitted,
            answer_key=key,
            exam_type=exam_type,
        )
        assert result["raw_score"] == raw
        assert result["band_score"] == expected, (
            f"raw={raw} exam_type={exam_type}: "
            f"got {result['band_score']}, expected {expected}"
        )

    def test_academic_band_0(self) -> None:
        self._check_band(0, "academic", 0.0)

    def test_academic_band_10(self) -> None:
        self._check_band(10, "academic", 4.0)

    def test_academic_band_20(self) -> None:
        self._check_band(20, "academic", 5.5)

    def test_academic_band_30(self) -> None:
        self._check_band(30, "academic", 7.0)

    def test_academic_band_35(self) -> None:
        self._check_band(35, "academic", 8.0)

    def test_academic_band_39(self) -> None:
        self._check_band(39, "academic", 9.0)

    def test_academic_band_40(self) -> None:
        self._check_band(40, "academic", 9.0)

    def test_general_band_0(self) -> None:
        self._check_band(0, "general", 0.0)

    def test_general_band_10(self) -> None:
        self._check_band(10, "general", 3.0)

    def test_general_band_20(self) -> None:
        self._check_band(20, "general", 4.5)

    def test_general_band_30(self) -> None:
        self._check_band(30, "general", 6.0)

    def test_general_band_35(self) -> None:
        self._check_band(35, "general", 7.0)

    def test_general_band_39(self) -> None:
        self._check_band(39, "general", 8.5)

    def test_general_band_40(self) -> None:
        self._check_band(40, "general", 9.0)


class TestSectionBreakdown:
    def test_sections_map_to_correct_ranges(self) -> None:
        gs = GradingService()
        key = {str(i): "A" for i in range(1, 41)}
        submitted = {str(i): "A" for i in range(1, 41)}
        result = gs.grade_reading(
            submitted_answers=submitted,
            answer_key=key,
        )
        assert result["section_breakdown"]["section_1"] == {
            "correct": 13,
            "total": 13,
        }
        assert result["section_breakdown"]["section_2"] == {
            "correct": 13,
            "total": 13,
        }
        assert result["section_breakdown"]["section_3"] == {
            "correct": 14,
            "total": 14,
        }

    def test_partial_sections(self) -> None:
        gs = GradingService()
        key = {str(i): "A" for i in range(1, 41)}
        submitted = {str(i): "A" for i in range(1, 14)}
        for i in range(14, 41):
            submitted[str(i)] = "WRONG"
        result = gs.grade_reading(
            submitted_answers=submitted,
            answer_key=key,
        )
        assert result["section_breakdown"]["section_1"]["correct"] == 13
        assert result["section_breakdown"]["section_2"]["correct"] == 0
        assert result["section_breakdown"]["section_3"]["correct"] == 0


class TestPerQuestionResult:
    def test_per_question_result_structure(self) -> None:
        gs = GradingService()
        result = gs.grade_reading(
            submitted_answers={"1": "A", "2": "WRONG"},
            answer_key={"1": "A", "2": "B"},
        )
        q1 = result["per_question_result"]["1"]
        assert q1["submitted_answer"] == "A"
        assert q1["correct_answer"] == "A"
        assert q1["is_correct"] is True

        q2 = result["per_question_result"]["2"]
        assert q2["submitted_answer"] == "WRONG"
        assert q2["correct_answer"] == "B"
        assert q2["is_correct"] is False

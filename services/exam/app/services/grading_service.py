import re
from typing import Any


class GradingService:
    LISTENING_BAND_BY_RAW_SCORE = (
        (39, 9.0),
        (37, 8.5),
        (35, 8.0),
        (32, 7.5),
        (30, 7.0),
        (26, 6.5),
        (23, 6.0),
        (18, 5.5),
        (16, 5.0),
        (13, 4.5),
        (10, 4.0),
        (0, 0.0),
    )

    READING_ACADEMIC_BAND_BY_RAW_SCORE = (
        (39, 9.0),
        (37, 8.5),
        (35, 8.0),
        (33, 7.5),
        (30, 7.0),
        (27, 6.5),
        (23, 6.0),
        (19, 5.5),
        (15, 5.0),
        (13, 4.5),
        (10, 4.0),
        (6, 3.5),
        (4, 3.0),
        (3, 2.5),
        (2, 2.0),
        (0, 0.0),
    )

    READING_GENERAL_BAND_BY_RAW_SCORE = (
        (40, 9.0),
        (39, 8.5),
        (37, 8.0),
        (36, 7.5),
        (34, 7.0),
        (32, 6.5),
        (30, 6.0),
        (27, 5.5),
        (23, 5.0),
        (19, 4.5),
        (15, 4.0),
        (12, 3.5),
        (9, 3.0),
        (6, 2.5),
        (3, 2.0),
        (0, 0.0),
    )

    READING_BAND_BY_RAW_SCORE = READING_ACADEMIC_BAND_BY_RAW_SCORE

    READING_SECTION_RANGES = {
        "section_1": (1, 13),
        "section_2": (14, 26),
        "section_3": (27, 40),
    }

    def grade(
        self,
        submitted_answers: dict[str, Any],
        answer_key: dict[str, Any],
        skill_area: str | None = None,
    ) -> dict[str, Any]:
        expected_answers = self._extract_answers(answer_key)
        submitted = self._extract_answers(submitted_answers)

        section_scores: dict[str, dict[str, int]] = {}
        raw_score = 0

        for answer_id, expected_value in expected_answers.items():
            submitted_value = submitted.get(answer_id)
            is_correct = self._matches(submitted_value, expected_value)
            raw_score += int(is_correct)

            section = self._section_for_answer(answer_id)
            section_score = section_scores.setdefault(
                section,
                {"correct": 0, "total": 0},
            )
            section_score["correct"] += int(is_correct)
            section_score["total"] += 1

        band_score = self.calculate_band_score(
            raw_score=raw_score,
            total_questions=len(expected_answers),
            skill_area=skill_area,
        )

        return {
            "raw_score": raw_score,
            "band_score": band_score,
            "section_scores": section_scores,
        }

    def grade_reading(
        self,
        submitted_answers: dict[str, str],
        answer_key: dict[str, Any],
        exam_type: str = "academic",
    ) -> dict[str, Any]:
        expected = self._extract_answers(answer_key)

        per_question_result: dict[str, dict[str, Any]] = {}
        section_breakdown: dict[str, dict[str, int]] = {
            name: {"correct": 0, "total": 0} for name in self.READING_SECTION_RANGES
        }
        raw_score = 0

        for q_key, correct_value in expected.items():
            submitted_value = submitted_answers.get(q_key, "")
            is_correct = self._matches_strict(submitted_value, correct_value)
            raw_score += int(is_correct)

            correct_display = (
                correct_value if isinstance(correct_value, str) else str(correct_value)
            )
            per_question_result[q_key] = {
                "submitted_answer": submitted_value,
                "correct_answer": correct_display,
                "is_correct": is_correct,
            }

            section = self._reading_section_for(q_key)
            section_breakdown[section]["total"] += 1
            section_breakdown[section]["correct"] += int(is_correct)

        band_table = self._reading_band_table(exam_type)
        band_score = self._lookup_band(raw_score, band_table)

        return {
            "raw_score": raw_score,
            "band_score": band_score,
            "per_question_result": per_question_result,
            "section_breakdown": section_breakdown,
        }

    def calculate_band_score(
        self,
        raw_score: int,
        total_questions: int,
        skill_area: str | None = None,
    ) -> float:
        if total_questions <= 0:
            return 0.0

        normalized_raw_score = round((raw_score / total_questions) * 40)
        band_table = self._band_table(skill_area)

        for minimum_score, band_score in band_table:
            if normalized_raw_score >= minimum_score:
                return band_score

        return 0.0

    def _reading_band_table(self, exam_type: str) -> tuple[tuple[int, float], ...]:
        if exam_type == "general":
            return self.READING_GENERAL_BAND_BY_RAW_SCORE
        return self.READING_ACADEMIC_BAND_BY_RAW_SCORE

    def _lookup_band(
        self,
        raw_score: int,
        band_table: tuple[tuple[int, float], ...],
    ) -> float:
        for minimum_score, band in band_table:
            if raw_score >= minimum_score:
                return band
        return 0.0

    def _band_table(self, skill_area: str | None) -> tuple[tuple[int, float], ...]:
        if skill_area == "reading":
            return self.READING_ACADEMIC_BAND_BY_RAW_SCORE
        return self.LISTENING_BAND_BY_RAW_SCORE

    def _extract_answers(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        answers = payload.get("answers")
        if isinstance(answers, dict):
            return self._flatten_answers(answers)

        return self._flatten_answers(payload)

    def _flatten_answers(
        self,
        payload: dict[str, Any],
        prefix: str | None = None,
    ) -> dict[str, Any]:
        flattened: dict[str, Any] = {}

        for key, value in payload.items():
            answer_id = str(key) if prefix is None else f"{prefix}.{key}"
            if isinstance(value, dict):
                flattened.update(self._flatten_answers(value, answer_id))
            else:
                flattened[answer_id] = value

        return flattened

    def _matches(self, submitted_value: Any, expected_value: Any) -> bool:
        if isinstance(expected_value, list):
            normalized_submitted = self._normalize_answer(submitted_value)
            return any(
                normalized_submitted == self._normalize_answer(option)
                for option in expected_value
            )

        return self._normalize_answer(submitted_value) == self._normalize_answer(
            expected_value
        )

    def _matches_strict(self, submitted_value: Any, expected_value: Any) -> bool:
        normalized = self._normalize_strict(submitted_value)
        if isinstance(expected_value, list):
            return any(
                normalized == self._normalize_strict(opt) for opt in expected_value
            )
        return normalized == self._normalize_strict(expected_value)

    def _normalize_answer(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "|".join(sorted(self._normalize_answer(item) for item in value))
        return " ".join(str(value).strip().lower().split())

    def _normalize_strict(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        text = re.sub(r"\s+", " ", text).strip().upper()
        return text

    def _section_for_answer(self, answer_id: str) -> str:
        if "." in answer_id:
            return answer_id.split(".", 1)[0]
        return "overall"

    def _reading_section_for(self, q_key: str) -> str:
        try:
            q_num = int(re.sub(r"\D", "", q_key))
        except (ValueError, TypeError):
            return "section_1"

        for section_name, (low, high) in self.READING_SECTION_RANGES.items():
            if low <= q_num <= high:
                return section_name
        return "section_3"

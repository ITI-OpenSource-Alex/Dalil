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

    READING_BAND_BY_RAW_SCORE = (
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
        (0, 0.0),
    )

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

    def _band_table(self, skill_area: str | None) -> tuple[tuple[int, float], ...]:
        if skill_area == "reading":
            return self.READING_BAND_BY_RAW_SCORE
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

    def _normalize_answer(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "|".join(sorted(self._normalize_answer(item) for item in value))
        return " ".join(str(value).strip().lower().split())

    def _section_for_answer(self, answer_id: str) -> str:
        if "." in answer_id:
            return answer_id.split(".", 1)[0]
        return "overall"

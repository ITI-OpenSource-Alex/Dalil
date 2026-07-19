"""
app/ingestion/writing_parser.py
-------------------------------
Cambridge IELTS Writing prompt parser.

Extracts Task 1 (letter/report/graph description) and Task 2 (essay) prompts
from Cambridge IELTS PDF or text content. Each test produces one record with
skill_area='writing', questions JSONB containing task 1 + task 2, and
time_limit_seconds=3600.
"""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.parser import BaseParser


class WritingParser(BaseParser):
    """Extracts IELTS Writing Task 1 and Task 2 prompts."""

    def parse_text(self, content: str | Any) -> dict[str, Any]:
        text = str(content)
        metadata = self._infer_metadata(text)
        metadata["skill_area"] = "writing"

        task1_prompt = self._extract_task(text, task_number=1)
        task2_prompt = self._extract_task(text, task_number=2)

        questions: list[dict[str, Any]] = []
        if task1_prompt:
            questions.append(
                {
                    "number": 1,
                    "prompt": task1_prompt,
                    "question_type": "Writing Task 1",
                    "instructions": self._detect_task1_type(task1_prompt),
                    "passage_number": None,
                    "section_number": None,
                }
            )
        if task2_prompt:
            questions.append(
                {
                    "number": 2,
                    "prompt": task2_prompt,
                    "question_type": "Writing Task 2",
                    "instructions": "Write an essay of at least 250 words.",
                    "passage_number": None,
                    "section_number": None,
                }
            )

        return {
            "book_ref": metadata.get("book_ref", "IELTS-unknown"),
            "test_number": metadata.get("test_number", 1),
            "exam_type": metadata.get("exam_type", "academic"),
            "skill_area": "writing",
            "passage_text": None,
            "questions": questions,
            "answer_key": {},
            "time_limit_seconds": 3600,
        }

    def _extract_task(self, text: str, *, task_number: int) -> str | None:
        patterns = [
            re.compile(
                rf"(?i)WRITING\s+TASK\s+{task_number}\b(.*?)(?=WRITING\s+TASK\s+|$)",
                re.DOTALL,
            ),
            re.compile(
                rf"(?i)TASK\s+{task_number}\b(.*?)(?=TASK\s+\d|$)",
                re.DOTALL,
            ),
        ]

        for pattern in patterns:
            m = pattern.search(text)
            if m:
                block = m.group(1).strip()
                prompt = self._clean_prompt(block)
                if prompt and len(prompt) > 20:
                    return prompt

        return None

    def _clean_prompt(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?i)^(you should spend|write at least)", stripped):
                lines.append(stripped)
                continue
            if re.match(r"(?i)^(page \d|copyright)", stripped):
                continue
            lines.append(stripped)
        return "\n".join(lines)

    def _detect_task1_type(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "letter" in lowered:
            return "Write a letter of at least 150 words."
        if "graph" in lowered or "chart" in lowered or "diagram" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        if "map" in lowered or "plan" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        if "process" in lowered or "flow" in lowered:
            return "Summarise the information by selecting and reporting the main features."
        return "Write at least 150 words."

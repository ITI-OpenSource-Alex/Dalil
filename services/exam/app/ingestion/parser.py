from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ingestion.ocr_service import OcrService

logger = logging.getLogger("exam_service.ingestion.parser")


@dataclass(slots=True)
class ParsedQuestion:
    prompt: str
    question_type: str
    answer: str | None = None
    number: int | None = None
    instructions: str | None = None
    passage_number: int | None = None
    section_number: int | None = None


@dataclass(slots=True)
class ParsedTest:
    book_ref: str
    test_number: int
    exam_type: str
    skill_area: str
    passage_text: str | None = None
    questions: list[ParsedQuestion] = field(default_factory=list)
    answer_key: dict[str, Any] = field(default_factory=dict)
    section_type: str | None = None
    audio_s3_key: str | None = None
    time_limit_seconds: int | None = None


class BaseParser:
    SUPPORTED_QUESTION_TYPES = {
        "Multiple Choice": "Multiple Choice",
        "Matching Headings": "Matching Headings",
        "Matching Information": "Matching Information",
        "Matching Features": "Matching Features",
        "Matching Sentence Endings": "Matching Sentence Endings",
        "True / False / Not Given": "True / False / Not Given",
        "Yes / No / Not Given": "Yes / No / Not Given",
        "Sentence Completion": "Sentence Completion",
        "Summary Completion": "Summary Completion",
        "Notes Completion": "Notes Completion",
        "Table Completion": "Table Completion",
        "Flow Chart Completion": "Flow Chart Completion",
        "Diagram Labelling": "Diagram Labelling",
        "Short Answer": "Short Answer",
    }

    def __init__(self) -> None:
        self._ocr_service = OcrService()

    def parse(self, content: str | Path) -> dict[str, Any]:
        return self.parse_text(content)

    def parse_text(self, content: str | Path) -> dict[str, Any]:
        raise NotImplementedError

    def parse_pdf(
        self,
        path: str | Path,
        *,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> dict[str, Any]:
        source_path = Path(path)
        text = self._ocr_service.extract(
            source_path, first_page=first_page, last_page=last_page
        )

        try:
            name = source_path.name
        except Exception:
            name = str(path)
        content = f"{name}\n{text}"
        return self.parse_text(content)

    def _normalize_text(self, text: str) -> str:
        return self._ocr_service.normalize_text(text)

    def _infer_metadata(
        self, content: str, source: str | None = None
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "book_ref": "IELTS-unknown",
            "test_number": 1,
            "exam_type": "academic",
            "skill_area": "reading",
        }
        text = content.lower()
        source_text = (source or "").lower()

        if re.search(r"ielts\s*(\d{1,2})", content, re.IGNORECASE):
            book_number = re.search(r"ielts\s*(\d{1,2})", content, re.IGNORECASE).group(
                1
            )
            metadata["book_ref"] = f"IELTS-{book_number}"
        elif re.search(r"ielts\s*(\d{1,2})", source_text, re.IGNORECASE):
            book_number = re.search(
                r"ielts\s*(\d{1,2})", source_text, re.IGNORECASE
            ).group(1)
            metadata["book_ref"] = f"IELTS-{book_number}"

        test_match = re.search(r"test\s*(\d+)", content, re.IGNORECASE)
        if test_match:
            metadata["test_number"] = int(test_match.group(1))
        elif re.search(r"test\s*(\d+)", source_text, re.IGNORECASE):
            metadata["test_number"] = int(
                re.search(r"test\s*(\d+)", source_text, re.IGNORECASE).group(1)
            )

        if "academic" in text:
            metadata["exam_type"] = "academic"
        elif "general" in text:
            metadata["exam_type"] = "general"
        if "academic" in source_text:
            metadata["exam_type"] = "academic"
        elif "general" in source_text:
            metadata["exam_type"] = "general"

        return metadata

    def _parse_answer_key(self, value: str) -> dict[str, Any]:
        answers: dict[str, Any] = {}
        for match in re.finditer(r"(\d+)\.\s*([^\d|]+)", value.strip()):
            answers[match.group(1)] = match.group(2).strip()
        return answers

    def _extract_answer_key(self, content: str) -> dict[str, Any]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        answers: dict[str, Any] = {}
        in_key_section = False
        for line in lines:
            lowered = line.lower()
            if (
                lowered.startswith("answer key")
                or lowered.startswith("answer keys")
                or lowered.startswith("answers")
            ):
                in_key_section = True
                continue
            if in_key_section and re.match(
                r"^(reading|listening|section|passage)\b", lowered
            ):
                break
            if in_key_section:
                match = re.match(r"^(\d{1,2})\s*[\.)]\s*(.+)$", line)
                if match:
                    answers[match.group(1)] = match.group(2).strip()
                    continue
                match = re.match(r"^(\d{1,2})\s+([A-Za-z0-9/\-() .]+)$", line)
                if match:
                    answers[match.group(1)] = match.group(2).strip()

        return answers

    def _classify_question_type(self, prompt: str) -> str:
        lowered = prompt.lower()
        if "short answer" in lowered or "no more than two words" in lowered:
            return "Short Answer"
        if "matching headings" in lowered or "choose the correct heading" in lowered:
            return "Matching Headings"
        if (
            "matching information" in lowered
            or "information" in lowered
            and "match" in lowered
        ):
            return "Matching Information"
        if (
            "matching features" in lowered
            or "features" in lowered
            and "match" in lowered
        ):
            return "Matching Features"
        if "matching sentence endings" in lowered or "sentence endings" in lowered:
            return "Matching Sentence Endings"
        if (
            "true / false / not given" in lowered
            or "true false not given" in lowered
            or "true / false" in lowered
        ):
            return "True / False / Not Given"
        if "yes / no / not given" in lowered or "yes no not given" in lowered:
            return "Yes / No / Not Given"
        if "complete the sentence" in lowered or "sentence completion" in lowered:
            return "Sentence Completion"
        if "complete the summary" in lowered or "summary completion" in lowered:
            return "Summary Completion"
        if "complete the notes" in lowered or "notes completion" in lowered:
            return "Notes Completion"
        if "complete the table" in lowered or "table completion" in lowered:
            return "Table Completion"
        if "flow chart" in lowered or "flow-chart" in lowered:
            return "Flow Chart Completion"
        if (
            "label the diagram" in lowered
            or "diagram" in lowered
            and "label" in lowered
        ):
            return "Diagram Labelling"
        if (
            "choose the correct letter" in lowered
            or "which of the following" in lowered
            or "choose the correct option" in lowered
        ):
            return "Multiple Choice"
        if "choose the correct heading" in lowered:
            return "Matching Headings"
        if "complete" in lowered or "fill" in lowered or "one word" in lowered:
            return "Sentence Completion"
        return "Multiple Choice"

    def _question_payload(self, question: ParsedQuestion) -> dict[str, Any]:
        return {
            "number": question.number,
            "prompt": question.prompt,
            "question_type": question.question_type,
            "instructions": question.instructions,
            "passage_number": question.passage_number,
            "section_number": question.section_number,
        }

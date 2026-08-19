from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ingestion.listening_parser import ListeningParser
from app.ingestion.reading_parser import ReadingParser
from app.ingestion.speaking_parser import SpeakingParser
from app.ingestion.writing_parser import WritingParser
from app.repositories.question_repository import QuestionRepository


class QuestionLoader:
    def __init__(self, repository: QuestionRepository):
        self.repository = repository
        self.reading_parser = ReadingParser()
        self.listening_parser = ListeningParser()
        self.writing_parser = WritingParser()
        self.speaking_parser = SpeakingParser()

    async def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = await self.repository.upsert_question(
            {
                "book_ref": payload["book_ref"],
                "test_number": payload["test_number"],
                "exam_type": payload.get("exam_type", "academic"),
                "skill_area": payload.get("skill_area", "reading"),
                "passage_text": payload.get("passage_text"),
                "audio_s3_key": payload.get("audio_s3_key"),
                "image_s3_key": payload.get("image_s3_key"),
                "questions": payload.get("questions", []),
                "answer_key": payload.get("answer_key", {}),
            }
        )
        return self._normalize_record(record)

    async def ingest_directory(self, directory: str | Path) -> list[dict[str, Any]]:
        root = Path(directory)
        ingested: list[dict[str, Any]] = []

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".txt", ".md"}:
                continue

            skill_area = self._infer_skill_area(path)
            if skill_area is None:
                continue

            if path.suffix.lower() == ".pdf":
                parsed = self._parser_for(skill_area).parse_pdf(path)
            else:
                parsed = self._parser_for(skill_area).parse_text(
                    path.read_text(encoding="utf-8")
                )

            record = await self.save(parsed)
            ingested.append(record)

        return ingested

    def _infer_skill_area(self, path: Path) -> str | None:
        lowered = str(path).lower()
        if "listening" in lowered:
            return "listening"
        if "reading" in lowered:
            return "reading"
        if "writing" in lowered:
            return "writing"
        if "speaking" in lowered:
            return "speaking"
        return None

    def _parser_for(
        self, skill_area: str
    ) -> ReadingParser | ListeningParser | WritingParser | SpeakingParser:
        if skill_area == "listening":
            return self.listening_parser
        if skill_area == "writing":
            return self.writing_parser
        if skill_area == "speaking":
            return self.speaking_parser
        return self.reading_parser

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record.get("id"),
            "book_ref": record["book_ref"],
            "test_number": record["test_number"],
            "exam_type": record["exam_type"],
            "skill_area": record["skill_area"],
            "passage_text": record.get("passage_text"),
            "audio_s3_key": record.get("audio_s3_key"),
            "image_s3_key": record.get("image_s3_key"),
            "questions": record.get("questions", []),
            "answer_key": record.get("answer_key", {}),
        }

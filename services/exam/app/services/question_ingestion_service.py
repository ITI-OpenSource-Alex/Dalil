from __future__ import annotations

from typing import Any

from app.ingestion.listening_parser import ListeningParser
from app.ingestion.reading_parser import ReadingParser
from app.ingestion.speaking_parser import SpeakingParser
from app.ingestion.writing_parser import WritingParser


class QuestionIngestionService:
    def __init__(self, repository: Any):
        self.repository = repository
        self.reading_parser = ReadingParser()
        self.listening_parser = ListeningParser()
        self.writing_parser = WritingParser()
        self.speaking_parser = SpeakingParser()

    async def ingest(self, content: str, *, skill_area: str) -> dict[str, Any]:
        if skill_area == "reading":
            parsed = self.reading_parser.parse(content)
        elif skill_area == "listening":
            parsed = self.listening_parser.parse(content)
        elif skill_area == "writing":
            parsed = self.writing_parser.parse(content)
        elif skill_area == "speaking":
            parsed = self.speaking_parser.parse(content)
        else:
            raise ValueError(f"Unsupported skill area: {skill_area}")

        return await self.repository.upsert_question(parsed)

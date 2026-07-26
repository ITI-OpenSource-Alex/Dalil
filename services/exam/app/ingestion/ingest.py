from __future__ import annotations

from pathlib import Path
from typing import Any

from app.ingestion.loader import QuestionLoader
from app.repositories.question_repository import QuestionRepository


class IngestionService:
    def __init__(self, repository: QuestionRepository):
        self.repository = repository
        self.loader = QuestionLoader(repository)

    async def ingest(self, content: str, *, skill_area: str) -> dict[str, Any]:
        parser = self.loader._parser_for(skill_area)
        parsed = parser.parse_text(content)
        return await self.loader.save(parsed)

    async def ingest_directory(self, directory: str | Path) -> list[dict[str, Any]]:
        return await self.loader.ingest_directory(directory)


def ingest_question_bank(
    content: str, *, skill_area: str, repository: QuestionRepository
) -> Any:
    service = IngestionService(repository)
    return service.ingest(content, skill_area=skill_area)

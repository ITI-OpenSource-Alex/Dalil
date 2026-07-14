from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.database import db
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_question_repository() -> QuestionRepository:
    return QuestionRepository(db.pool)


@router.get("/question-bank/stats")
async def question_bank_stats(
    repository: QuestionRepository = Depends(get_question_repository),
) -> dict[str, Any]:
    raw_stats = await repository.get_question_bank_stats()
    book_stats = await repository.get_question_bank_stats_by_book()

    payload: dict[str, dict[str, int]] = {"academic": {}, "general": {}}

    for row in raw_stats:
        exam_type = row["exam_type"]
        skill_area = row["skill_area"]
        payload.setdefault(exam_type, {})
        payload[exam_type][skill_area] = payload[exam_type].get(skill_area, 0) + row["count"]

    if not raw_stats:
        payload["academic"]["reading"] = 1
        payload["academic"]["listening"] = 0
        payload["general"]["reading"] = 0
        payload["general"]["listening"] = 0

    for skill in ("reading", "listening", "writing", "speaking"):
        if skill not in payload.get("academic", {}):
            payload.setdefault("academic", {})[skill] = 0
        if skill not in payload.get("general", {}):
            payload.setdefault("general", {})[skill] = 0

    by_book: dict[str, dict[str, dict[str, int]]] = {}
    for row in book_stats:
        book = row["book_ref"]
        exam_type = row["exam_type"]
        skill_area = row["skill_area"]
        by_book.setdefault(book, {}).setdefault(exam_type, {})[skill_area] = row["count"]

    return {**payload, "by_book": by_book}

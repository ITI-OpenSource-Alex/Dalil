import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import db
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.schemas.common import ExamType, SkillArea
from app.schemas.question import QuestionResponse

router = APIRouter(
    prefix="/questions",
    tags=["questions"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_question_repository() -> QuestionRepository:
    return QuestionRepository(db.pool)


@router.get("/random")
async def get_random_question(
    exam_type: ExamType,
    skill_area: SkillArea,
    repository: QuestionRepository = Depends(get_question_repository),
) -> dict[str, Any]:
    question = await repository.get_random_question(
        exam_type=exam_type.value,
        skill_area=skill_area.value,
    )
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    return QuestionResponse.model_validate(
        {
            "id": question["id"],
            "book_ref": question["book_ref"],
            "test_number": question["test_number"],
            "exam_type": question["exam_type"],
            "skill_area": question["skill_area"],
            "passage_text": question["passage_text"],
            "audio_s3_key": question["audio_s3_key"],
            "questions": _question_list(question["questions"]),
        }
    ).model_dump()


def _question_list(value: Any) -> list[dict[str, Any]]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if decoded is None:
        return []
    if isinstance(decoded, list):
        return decoded
    if isinstance(decoded, dict):
        nested_questions = decoded.get("questions")
        if isinstance(nested_questions, list):
            return nested_questions
        return [decoded]
    return []

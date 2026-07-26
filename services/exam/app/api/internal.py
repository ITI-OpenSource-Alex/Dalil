from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import structlog

from app.core.config import settings
from app.core.database import db
from app.core.metrics import (
    goa_speaking_exam_evaluation_ms,
    goa_speaking_exam_evaluations_total,
)
from app.core.security import validate_internal_api_key
from app.repositories.question_repository import QuestionRepository
from app.repositories.result_repository import ResultRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.services.speaking_client import SpeakingServiceClient


logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_question_repository() -> QuestionRepository:
    return QuestionRepository(db.pool)


class TranscriptPayload(BaseModel):
    part: int
    transcript_text: str
    duration_s: int
    question_text: str


class Example(BaseModel):
    part: int
    quote: str
    issue: str


class CriterionDetail(BaseModel):
    criterion: str
    band: float
    overall_feedback: str
    part_notes: dict[str, str]
    examples: list[Example]
    improvement_tip: str
    timed_out: bool


class EvaluationResponse(BaseModel):
    status: str
    partial: bool
    overall_band: float
    dimensions: dict[str, CriterionDetail]
    overall_feedback: str


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
        payload[exam_type][skill_area] = (
            payload[exam_type].get(skill_area, 0) + row["count"]
        )

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
        by_book.setdefault(book, {}).setdefault(exam_type, {})[skill_area] = row[
            "count"
        ]

    return {**payload, "by_book": by_book}


@router.get("/sessions/{session_id}/owner")
async def get_session_owner(session_id: UUID):
    session_repo = SessionRepository(db.pool)
    res = await session_repo.get_by_id(session_id)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return {"user_id": str(res["user_id"])}


@router.post("/sessions/{session_id}/speaking/transcripts")
async def submit_transcript(session_id: UUID, payload: TranscriptPayload):
    if payload.part == 2 and payload.duration_s < 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad Request",
        )

    session_repo = SessionRepository(db.pool)
    sessions_res = await session_repo.get_by_id(session_id)
    if not sessions_res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    if sessions_res["status"] in ("submitted", "scored"):
        return {}

    transcript_repo = TranscriptRepository(db.pool)
    await transcript_repo.create_or_update(
        session_id,
        payload.part,
        payload.transcript_text,
        payload.duration_s,
        payload.question_text,
    )

    if payload.part in (1, 2):
        return {}

    if payload.part == 3:
        if not await session_repo.try_submit(session_id):
            return {}

        transcripts = await transcript_repo.get_all_for_session(session_id)
        text = "\n".join(
            [f"Part {t['part']}:\n{t['transcript_text']}" for t in transcripts]
        )

        speaking_client = SpeakingServiceClient(
            settings.speaking_service_url, settings.internal_api_key
        )
        start_time = time.time()
        result = await speaking_client.evaluate_holistic(
            session_id, {"concatenated_transcript": text, "user_id": str(sessions_res["user_id"])}
        )
        duration_ms = (time.time() - start_time) * 1000
        goa_speaking_exam_evaluation_ms.observe(duration_ms)
        goa_speaking_exam_evaluations_total.labels(status="success").inc()

        eval_data = EvaluationResponse.model_validate(result)
        section_scores = {k: v.band for k, v in eval_data.dimensions.items()}

        result_repo = ResultRepository(db.pool)
        await result_repo.create(
            result_id=uuid4(),
            session_id=session_id,
            user_id=sessions_res["user_id"],
            skill_area=sessions_res["skill_area"],
            raw_score=0,
            band_score=eval_data.overall_band,
            section_scores=section_scores,
            agent_responses=eval_data.model_dump(),
        )
        await session_repo.mark_scored(session_id)

        return {}

    return {}

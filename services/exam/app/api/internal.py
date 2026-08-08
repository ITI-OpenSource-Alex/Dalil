from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import structlog

import httpx

from app.core.config import settings
from app.core.database import db
from app.core.exam_observability import (
    record_exam_completion,
    refresh_question_bank_size,
)
from app.services.account_deletion import export_user_data, purge_user_data
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
from app.services.transcript_prosody import merge_part_timings


logger = structlog.get_logger(__name__)
router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(validate_internal_api_key)],
)


def get_question_repository() -> QuestionRepository:
    return QuestionRepository(db.pool)


class WordTiming(BaseModel):
    word: str
    start: float
    end: float
    probability: float = 0.0


class TranscriptPayload(BaseModel):
    part: int
    transcript_text: str
    duration_s: int
    question_text: str
    # GOA-133. Optional, so a producer that has not been updated keeps working.
    # When absent the evaluator omits the measured-feature block and the Fluency
    # and Pronunciation prompts say so, rather than inferring delivery from text.
    words: list[WordTiming] | None = None
    audio_duration_s: float | None = None


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
    # GOA-134. Optional, and absent-by-default rather than required.
    #
    # The speaking service emits `overall_band` with `omitempty` and drops the key
    # entirely when fewer than 3 of 4 criteria completed, so a required `float`
    # here raises ValidationError and breaks the exam speaking flow outright. The
    # two services must agree that "not scored" is representable; before this it
    # was representable on neither side, so a band was fabricated instead.
    overall_band: float | None = None
    # How many criteria produced a real score. Lets a reader tell 4-of-4 from
    # 1-of-4 without inferring it from `partial`.
    completed_count: int | None = None
    dimensions: dict[str, CriterionDetail]
    overall_feedback: str


@router.get("/question-bank/stats")
async def question_bank_stats(
    repository: QuestionRepository = Depends(get_question_repository),
) -> dict[str, Any]:
    raw_stats = await repository.get_question_bank_stats()
    book_stats = await repository.get_question_bank_stats_by_book()

    # Keep the gauge in step with the bank every time stats are queried.
    refresh_question_bank_size(raw_stats)

    payload: dict[str, dict[str, int]] = {"academic": {}, "general": {}}

    for row in raw_stats:
        exam_type = row["exam_type"]
        skill_area = row["skill_area"]
        payload.setdefault(exam_type, {})
        payload[exam_type][skill_area] = (
            payload[exam_type].get(skill_area, 0) + row["count"]
        )

    # An empty question bank must report zeros. This previously hardcoded
    # academic.reading = 1 whenever raw_stats came back empty, so the endpoint was
    # at its most confident precisely when there was nothing there: it reported
    # "1 academic reading test" against a `questions` table holding 0 rows, while
    # /exam/reading/start correctly answered "No reading tests available"
    # (BUG-020). The zero-fill below already handles absent keys.
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
        words=[w.model_dump() for w in payload.words] if payload.words else None,
        audio_duration_s=payload.audio_duration_s,
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

        # GOA-133: stitch each part's word timings onto one continuous timeline so
        # the Fluency and Pronunciation agents judge delivery from measurement
        # rather than from spelling. Empty when no part carried timings, in which
        # case the speaking service omits the feature block entirely rather than
        # rendering it as zeros.
        merged_words, merged_duration_s = merge_part_timings(transcripts)

        speaking_client = SpeakingServiceClient(
            settings.speaking_service_url, settings.internal_api_key
        )
        start_time = time.time()

        # GOA-134. try_submit above has already flipped the session to
        # 'submitted'. If anything below raises, the session is left submitted
        # with no result row and the guard at the top of this endpoint refuses
        # every retry -- the candidate's exam is gone and the endpoint returns
        # 200. Revert the submission on any failure so the part-3 post can be
        # retried, and re-raise so the caller learns the evaluation failed.
        try:
            result = await speaking_client.evaluate_holistic(
                session_id,
                {
                    "concatenated_transcript": text,
                    "user_id": str(sessions_res["user_id"]),
                    # Carried from dev: the speaking service tags its Langfuse
                    # trace with this so an exam evaluation is findable by session.
                    "exam_session_id": str(session_id),
                    "duration_s": merged_duration_s,
                    "words": merged_words,
                },
            )
            duration_ms = (time.time() - start_time) * 1000
            goa_speaking_exam_evaluation_ms.observe(duration_ms)

            eval_data = EvaluationResponse.model_validate(result)
            section_scores = {k: v.band for k, v in eval_data.dimensions.items()}

            result_repo = ResultRepository(db.pool)
            await result_repo.create(
                result_id=uuid4(),
                session_id=session_id,
                user_id=sessions_res["user_id"],
                skill_area=sessions_res["skill_area"],
                raw_score=0,
                # May be None when fewer than 3 criteria completed. Persisted as
                # NULL rather than 0.0 -- see migration 00X and the speaking
                # service's own 003_overall_band_nullable, which made the same
                # change for the same reason.
                band_score=eval_data.overall_band,
                section_scores=section_scores,
                agent_responses=eval_data.model_dump(),
            )
        except Exception as exc:
            reverted = await session_repo.revert_submission(session_id)
            outcome = (
                "timeout"
                if isinstance(exc, (httpx.TimeoutException, httpx.TransportError))
                else "error"
            )
            goa_speaking_exam_evaluations_total.labels(status=outcome).inc()
            logger.error(
                "speaking_holistic_evaluation_failed",
                session_id=str(session_id),
                outcome=outcome,
                reverted_to_in_progress=reverted,
                error=str(exc),
            )
            raise

        # Labelled by what actually came back. `success` alone could not
        # distinguish a full band from a partial evaluation, and the partial case
        # is the one that used to be invisible because a band was fabricated for it.
        goa_speaking_exam_evaluations_total.labels(
            status="success" if eval_data.overall_band is not None else "partial_unscored"
        ).inc()

        await session_repo.mark_scored(session_id)

        question_id = sessions_res.get("question_id")
        question = (
            await QuestionRepository(db.pool).get_by_id(question_id)
            if question_id
            else None
        )
        duration_s = sum(int(t.get("duration_s") or 0) for t in transcripts)
        record_exam_completion(
            session_id=session_id,
            user_id=sessions_res["user_id"],
            skill_area=sessions_res["skill_area"],
            exam_type=sessions_res["exam_type"],
            band_score=eval_data.overall_band,
            duration_s=duration_s,
            question_bank_ref=question.get("book_ref") if question else None,
        )

        return {}

    return {}


@router.get("/users/{user_id}/exam-history")
async def export_exam_user_data(user_id: UUID):
    return await export_user_data(db.pool, str(user_id))


@router.post("/users/{user_id}/purge")
async def purge_deleted_account(user_id: UUID):
    return await purge_user_data(db.pool, str(user_id))


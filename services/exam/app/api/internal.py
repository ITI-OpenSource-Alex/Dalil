from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from uuid import UUID, uuid4
from app.core.database import db
from app.core.config import settings
from app.repositories.session_repository import SessionRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.repositories.result_repository import ResultRepository
from app.services.speaking_client import SpeakingServiceClient
import structlog
from app.core.metrics import goa_speaking_exam_evaluations_total, goa_speaking_exam_evaluation_ms
import time



logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/internal/sessions", tags=["Internal"])


def validate_internal_api_key(x_internal_api_key: str = Header(...)):
    if x_internal_api_key == settings.internal_api_key:
        return x_internal_api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )



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


@router.get("/{session_id}/owner")
async def get_session_owner(
    session_id: UUID,
    api_key: str = Depends(validate_internal_api_key)
):

    session_repo = SessionRepository(db.pool)
    res = await session_repo.get_by_id(session_id)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    userId = res["user_id"]
    return {"user_id": str(userId)}




@router.post("/{session_id}/speaking/transcripts")
async def submit_transcript(
    session_id: UUID,
    payload: TranscriptPayload,
    api_key: str = Depends(validate_internal_api_key)
):
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
    if sessions_res["status"] in ('submitted', 'scored'):
        return {}

    transcript_repo = TranscriptRepository(db.pool)
    transcript_res = await transcript_repo.create_or_update(session_id, payload.part, payload.transcript_text, payload.duration_s, payload.question_text)


    if payload.part == 2 or payload.part == 1:
        return {}
    
    if payload.part == 3:
        # Atomic lock against double billing
        if not await session_repo.try_submit(session_id):
            return {}
            
        transcripts = await transcript_repo.get_all_for_session(session_id)
        text = "\n".join([f"Part {t['part']}:\n{t['transcript_text']}" for t in transcripts])


        speaking_client = SpeakingServiceClient(settings.speaking_service_url, settings.internal_api_key)
        start_time = time.time()
        result = await speaking_client.evaluate_holistic(session_id, {"concatenated_transcript": text})
        duration_ms = (time.time() - start_time) * 1000
        goa_speaking_exam_evaluation_ms.observe(duration_ms)
        goa_speaking_exam_evaluations_total.labels(status="success").inc()
        
        # Enforce agent response schema
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
            agent_responses=eval_data.model_dump()
        )
        await session_repo.mark_scored(session_id)

        return {}



    

from contextlib import nullcontext

from fastapi import APIRouter, Header
from app.schemas.scoring import ScoreRequest, MatchRequest
from app.services.scoring import calculate_score, match_programs
from app.services import rag_service
from app.core.trace_context import parse_traceparent
import structlog


logger = structlog.get_logger("rag_service.api.scoring")
router = APIRouter(tags=["scoring"])
match_router = APIRouter(tags = ["match"] )
@router.post("/score")
async def score_profile(
    request: ScoreRequest,
    traceparent: str | None = Header(None, alias="traceparent"),
):
    trace_scope = nullcontext(None)
    if rag_service.langfuse_client is not None:
        try:
            trace_scope = rag_service.langfuse_client.start_as_current_observation(
                trace_context=parse_traceparent(traceparent),
                name="rag-score",
                as_type="span",
                input=request.model_dump(),
            )
        except Exception as exc:
            logger.warning("langfuse_score_trace_start_failed", error=str(exc))

    with trace_scope as observation:
        result = await calculate_score(request.userId, request.programId)
        if observation is not None:
            try:
                observation.update(output=result)
            except Exception as exc:
                logger.warning("langfuse_score_trace_update_failed", error=str(exc))
        return result


@match_router.post("/match")
async def match_profile(
    request: MatchRequest,
    traceparent: str | None = Header(None, alias="traceparent"),
):
    """Filtered, batch-scored, ranked top-N matches.

    The previous implementation fanned out over every row in program_requirements with
    two queries per program; see match_programs() for why that could not survive the
    full catalog.
    """
    trace_scope = nullcontext(None)
    if rag_service.langfuse_client is not None:
        try:
            trace_scope = rag_service.langfuse_client.start_as_current_observation(
                trace_context=parse_traceparent(traceparent),
                name="rag-match",
                as_type="span",
                input=request.model_dump(),
            )
        except Exception as exc:
            logger.warning("langfuse_match_trace_start_failed", error=str(exc))

    with trace_scope as observation:
        programs = await match_programs(request.userId)
        if observation is not None:
            try:
                observation.update(output={"program_count": len(programs)})
            except Exception as exc:
                logger.warning("langfuse_match_trace_update_failed", error=str(exc))
    return {"programs": programs}

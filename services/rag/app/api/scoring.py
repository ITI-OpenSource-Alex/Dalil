from fastapi import APIRouter, HTTPException
from app.schemas.scoring import ScoreRequest, MatchRequest
from app.services.scoring import calculate_score, match_programs
from app.core.database import db
import structlog
import asyncio


logger = structlog.get_logger("rag_service.api.scoring")
router = APIRouter(tags=["scoring"])
match_router = APIRouter(tags = ["match"] )
@router.post("/score")
async def score_profile(request: ScoreRequest):
    return await calculate_score(request.userId, request.programId)


@match_router.post("/match")
async def match_profile(request: MatchRequest):
    """Filtered, batch-scored, ranked top-N matches.

    The previous implementation fanned out over every row in program_requirements with
    two queries per program; see match_programs() for why that could not survive the
    full catalog.
    """
    programs = await match_programs(request.userId)
    return {"programs": programs}

from fastapi import APIRouter, HTTPException
from app.schemas.scoring import ScoreRequest, MatchRequest
from app.services.scoring import calculate_score
from app.core.database import db
import structlog


logger = structlog.get_logger("rag_service.api.scoring")
router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/score")
async def score_profile(request: ScoreRequest):
    return await calculate_score(request.userId, request.programId)


@router.post("/match")
async def match_profile(request: MatchRequest):
    # 1. Fetch all program IDs in the database
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM program_requirements")
        program_ids = [str(r["id"]) for r in rows]

    results = []
    # 2. Score against every single program
    for pid in program_ids:
        try:
            res = await calculate_score(request.userId, pid)
            results.append({"programId": pid, "result": res})
        except HTTPException as e:
            # If a program is misconfigured or deleted mid-loop, just skip it gracefully
            logger.warning(
                f"Skipping program {pid} for user {request.userId}: {e.detail}"
            )
        except Exception as e:
            logger.error(f"Unexpected error scoring program {pid}: {str(e)}")

    # 3. Rank them from highest score to lowest score
    results.sort(key=lambda x: x["result"]["score"], reverse=True)

    return {"matches": results}

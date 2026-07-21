from fastapi import APIRouter, HTTPException
from app.schemas.scoring import ScoreRequest, MatchRequest
from app.services.scoring import calculate_score
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

    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, program_name, university, country, deadline, degree_level FROM program_requirements")
        programs_data = {}
        program_ids = []

        for r in rows:
            pid = str(r["id"])
            program_ids.append(pid)
            programs_data[pid] = {
            "programName": r["program_name"] or f"{r['university']} — {r['degree_level']}",
            "university": r["university"],
            "country": r["country"],
            "deadline": str(r["deadline"]) if r["deadline"] else None,
        }

    results = []
    semaphore = asyncio.Semaphore(5)


    async def score_program(pid):
        async with semaphore:
            try:
                res = await calculate_score(request.userId, pid, apply_llm_boost=False)
                return {
                    "programId": pid,
                    "programName": programs_data[pid]["programName"],
                    "university": programs_data[pid]["university"],
                    "country": programs_data[pid]["country"],
                    "deadline": programs_data[pid]["deadline"],
                    "result": res,
                }
            except HTTPException as e:
                # If calculate_score throws 404, it skips automatically returning None
                if e.status_code != 404:
                    logger.warning(f"Skipping program {pid} for user {request.userId}: {e.detail}")
            except Exception as e:
                logger.error(f"Unexpected error scoring program {pid}: {str(e)}")
            return None
    # 3. Fire them off concurrently
    tasks = [score_program(pid) for pid in program_ids]
    completed_results = await asyncio.gather(*tasks)
    
    # 4. Filter out any None (failures/404s)
    for r in completed_results:
        if r is not None:
            results.append(r)
    # 5. Sort from highest score to lowest
    results.sort(key=lambda x: x["result"]["score"], reverse=True)
    return {"programs": results}
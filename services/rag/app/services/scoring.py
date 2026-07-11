import time
import json
import structlog
from fastapi import HTTPException
from langfuse.decorators import observe, langfuse_context
from app.core.database import db
from app.core.redis import redis_client
from app.schemas.scoring import UserProfile, ProgramRequirements
from app.clients.user_client import get_user_profile, UserServiceUnavailable
from app.clients.writing_client import get_user_cv
from app.services.gates import check_hard_gates
from app.services.soft_score import compute_soft_score
from app.services.llm_boost import get_llm_boost
from app.services.gap_report import generate_gap_report
from app.core.metrics import SCORING_PIPELINE_LATENCY, LLM_BOOST_VALUE



logger = structlog.get_logger("rag_service.scoring")
# 1 Hour Cache TTL
CACHE_TTL = 3600


async def get_program_requirements(program_id: str) -> ProgramRequirements | None:
    # RAG service uses raw asyncpg SQL
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, min_ects, degree_level, required_citizenship, min_ielts, min_gpa, min_work_experience
            FROM program_requirements
            WHERE id = $1
        """, program_id)
        
        if not row:
            return None
            
        return ProgramRequirements(
            id=str(row["id"]),
            min_ects=row["min_ects"],
            degree_level=row["degree_level"],
            required_citizenship=row["required_citizenship"],
            min_ielts=row["min_ielts"],
            min_gpa=row["min_gpa"],
            min_work_experience=row["min_work_experience"]
        )

@observe(as_type="trace", name="GOA-012-scoring-pipeline")
async def calculate_score(user_id: str, program_id: str) -> dict:
    start_time = time.time()
    
    # 1. CACHE-FIRST PRECEDENCE
    cache_key = f"score:{user_id}:{program_id}"
    if redis_client.redis:
        cached_result = await redis_client.redis.get(cache_key)
        if cached_result:
            logger.info("Cache hit", user_id=user_id, program_id=program_id)
            return json.loads(cached_result)
            
    # 2. FETCH DATA (Handling 404s and explicit 503s)
    program = await get_program_requirements(program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
        
    try:
        user_data = await get_user_profile(user_id)
    except UserServiceUnavailable as e:
        # Crucial constraint: We do not mask 503 outages as 404s!
        raise HTTPException(status_code=503, detail=str(e))
        
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
        
    profile = UserProfile(**user_data)
    
    # 3. STAGE 1: HARD GATES
    gate_result = check_hard_gates(profile, program)
    
    if not gate_result.passed:
        final_result = {
            "score": 0.0,
            "blocked_by": gate_result.gateType,
            "gap_report": {gate_result.gateType: gate_result.reason}
        }
        soft_score = 0
        boost_value = 0
    else:
        # 4. STAGE 2: SOFT SCORE
        soft_score = compute_soft_score(profile, program)
        
        # 5. STAGE 3: LLM BOOST
        cv_text = await get_user_cv(user_id)
        llm_result = await get_llm_boost(cv_text=cv_text, program_description=str(program.model_dump()))
        boost_value = llm_result["boost_value"]
        
        # Calculate Final Score (Clamped strictly to 0-100)
        final_score = max(0.0, min(100.0, soft_score + boost_value))
        
        # 6. GAP REPORT
        gap_report = generate_gap_report(profile, program)
        if llm_result.get("justification_tokens"):
            gap_report["llm_feedback"] = llm_result["justification_tokens"]
            
        final_result = {
            "score": final_score,
            "blocked_by": None,
            "gap_report": gap_report
        }
        
    latency_ms = int((time.time() - start_time) * 1000)
    
    # 7. METRICS & TRACING: Inject into Langfuse parent trace
    langfuse_context.update_current_trace(
        user_id=user_id,
        metadata={
            "program_id": program_id,
            "stage1_passed": gate_result.passed,
            "final_score": final_result["score"],
            "latency_ms": latency_ms
        }
    )
    
    # STRUCTURED JSON LOG (Required for GOA-012 observability acceptance criteria)
    print(json.dumps({
        "user_id": user_id,
        "program_id": program_id,
        "stage1_passed": gate_result.passed,
        "stage2_score": soft_score,
        "stage3_boost": boost_value,
        "final_score": final_result["score"],
        "blocked_by": final_result["blocked_by"],
        "latency_ms": latency_ms
    }))
    SCORING_PIPELINE_LATENCY.observe(latency_ms)
    if gate_result.passed:
        LLM_BOOST_VALUE.observe(boost_value)
    # 8. SAVE TO CACHE
    if redis_client.redis:
        await redis_client.redis.set(cache_key, json.dumps(final_result), ex=CACHE_TTL)
        
    return final_result
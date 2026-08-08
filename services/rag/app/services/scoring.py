import time
import json
import structlog
from fastapi import HTTPException
from langfuse import get_client, observe
from app.core.database import db
from app.core.redis import redis_client
from app.schemas.scoring import UserProfile, ProgramRequirements
from app.clients.writing_client import get_user_cv
from app.services.gates import check_hard_gates
from app.services.soft_score import compute_soft_score
from app.services.llm_boost import get_llm_boost
from app.services.gap_report import generate_gap_report
from app.services.visa_finance import get_student_visa_finance
from app.core.metrics import SCORING_PIPELINE_LATENCY, LLM_BOOST_VALUE


logger = structlog.get_logger("rag_service.scoring")
# 1 Hour Cache TTL
CACHE_TTL = 3600

# Safety cap on how many programs one /match request will score after filtering.
# The catalog is ~20,000 in-scope European Engineering/CS programs; country and
# discipline filters normally cut that to tens, but an unfiltered profile (no target
# countries, no field of study) would otherwise score the whole table.
MATCH_CANDIDATE_CAP = 500

# How many ranked results /match returns. E2E RAG-05 specifies a top-10 list; before
# this there was no LIMIT at all and /match returned every program in the table.
MATCH_RESULT_LIMIT = 10

# Free-text field_of_study -> canonical discipline slug (migration 022). Substring
# match, first hit wins; an unrecognised field of study disables discipline filtering
# rather than silently matching nothing.
_FIELD_OF_STUDY_TO_DISCIPLINE = (
    ("computer_science", ("computer", "software", "informat", " it", "data scien", "artificial intelligence", "cyber")),
    ("engineering", ("engineer", "mechatron", "robotic")),
)


def discipline_for_field_of_study(field_of_study: str | None) -> str | None:
    """Map a profile's free-text field of study onto a discipline slug, or None."""
    if not field_of_study or not field_of_study.strip():
        return None
    text = f" {field_of_study.strip().lower()} "
    for slug, needles in _FIELD_OF_STUDY_TO_DISCIPLINE:
        if any(n in text for n in needles):
            return slug
    return None


def score_profile_against_program(
    profile: UserProfile,
    program: ProgramRequirements,
    finance_items: list[dict] | None = None,
) -> dict:
    """Stage 1 + Stage 2 scoring with no I/O — the shared core of /score and /match.

    Deliberately excludes Stage 3 (the LLM boost): GOA-125 removed it from /match for
    cost, and keeping this function I/O-free is what lets /match score a filtered
    candidate set in memory instead of issuing two queries per program.
    """
    gate_result = check_hard_gates(profile, program)
    if not gate_result.passed:
        return {
            "score": 0.0,
            "blocked_by": gate_result.gateType,
            "gap_report": {gate_result.gateType: gate_result.reason},
        }

    gap_report = generate_gap_report(profile, program)
    if finance_items:
        gap_report["financial"] = finance_items

    return {
        "score": compute_soft_score(profile, program),
        "blocked_by": None,
        "gap_report": gap_report,
    }


async def get_local_user_profile(user_id: str) -> dict | None:
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, ects, gpa, gpa_scale, ielts_score, degree_level, 
                   work_exp, extracurriculars, target_countries, field_of_study
            FROM local_user_profiles
            WHERE user_id = $1
        """,
            user_id,
        )

        if not row:
            return None

        # Map snake_case database columns back to camelCase for our Pydantic Schema!
        # user_id is a UUID column, so asyncpg hands back a uuid.UUID object — coerce to
        # str here or UserProfile.userId (typed str) rejects every real row.
        return {
            "userId": str(row["user_id"]),
            "ects": row["ects"],
            "gpa": row["gpa"],
            "gpaScale": row["gpa_scale"],
            "ieltsScore": row["ielts_score"],
            "degreeLevel": row["degree_level"],
            "workExperienceYears": row["work_exp"],
            "extracurricularsScore": row["extracurriculars"],
            "targetCountries": row["target_countries"] or [],
            "citizenship": None,
            # Drives /match discipline pre-filtering. Was hardcoded None, so the
            # filter could never activate no matter what the user had set.
            "fieldOfStudy": row["field_of_study"],
        }


async def get_program_requirements(program_id: str) -> ProgramRequirements | None:
    # RAG service uses raw asyncpg SQL
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, country, min_ects, degree_level, required_citizenship, min_ielts, min_gpa, min_work_experience
            FROM program_requirements
            WHERE id = $1
        """,
            program_id,
        )

        if not row:
            return None

        return ProgramRequirements(
            id=str(row["id"]),
            country=row["country"],
            min_ects=row["min_ects"],
            degree_level=row["degree_level"],
            required_citizenship=row["required_citizenship"],
            min_ielts=row["min_ielts"],
            min_gpa=row["min_gpa"],
            min_work_experience=row["min_work_experience"],
        )


@observe(as_type="span", name="GOA-012-scoring-pipeline")
async def calculate_score(user_id: str, program_id: str, apply_llm_boost: bool = True) -> dict:
    start_time = time.time()

    # CACHE-FIRST PRECEDENCE
    cache_key = f"score:{user_id}:{program_id}:boost_{apply_llm_boost}"
    if redis_client.redis:
        cached_result = await redis_client.redis.get(cache_key)
        if cached_result:
            logger.info("Cache hit", user_id=user_id, program_id=program_id)
            return json.loads(cached_result)

    # FETCH DATA (Handling 404s and explicit 503s)
    program = await get_program_requirements(program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")

    user_data = await get_local_user_profile(user_id)
    if not user_data:
        # Crucial: Return 425 Too Early because the SQS consumer hasn't replicated the user yet!
        raise HTTPException(
            status_code=425, detail="Profile not yet replicated. Please retry."
        )

    profile = UserProfile(**user_data)

    # STAGE 1: HARD GATES
    gate_result = check_hard_gates(profile, program)

    if not gate_result.passed:
        final_result = {
            "score": 0.0,
            "blocked_by": gate_result.gateType,
            "gap_report": {gate_result.gateType: gate_result.reason},
        }
        soft_score = 0
        boost_value = 0
    else:
        # STAGE 2: SOFT SCORE
        soft_score = compute_soft_score(profile, program)

        # STAGE 3: LLM BOOST
        if apply_llm_boost:
            cv_text = await get_user_cv(user_id)
            llm_result = await get_llm_boost(
                cv_text=cv_text, program_description=str(program.model_dump())
            )
            boost_value = llm_result["boost_value"]
            llm_feedback = llm_result.get("justification_tokens")
        else:
            boost_value = 0
            llm_feedback = None

        # Calculate Final Score (Clamped strictly to 0-100)
        final_score = max(0.0, min(100.0, soft_score + boost_value))

        # 6. GAP REPORT
        gap_report = generate_gap_report(profile, program)
        if llm_feedback:
            gap_report["llm_feedback"] = llm_feedback

        if getattr(program, "country", None):
            from app.services.visa_finance import get_student_visa_finance
            finance_items = await get_student_visa_finance(program.country)
            if finance_items:
                gap_report["financial"] = finance_items

        final_result = {
            "score": final_score,
            "blocked_by": None,
            "gap_report": gap_report,
        }

    latency_ms = int((time.time() - start_time) * 1000)

    # 7. METRICS & TRACING: Inject into Langfuse parent trace
    get_client().update_current_span(
        metadata={
            "user_id": user_id,
            "program_id": program_id,
            "stage1_passed": gate_result.passed,
            "final_score": final_result["score"],
            "latency_ms": latency_ms,
        },
    )

    # STRUCTURED JSON LOG (Required for GOA-012 observability acceptance criteria)
    print(
        json.dumps(
            {
                "user_id": user_id,
                "program_id": program_id,
                "stage1_passed": gate_result.passed,
                "stage2_score": soft_score,
                "stage3_boost": boost_value,
                "final_score": final_result["score"],
                "blocked_by": final_result["blocked_by"],
                "latency_ms": latency_ms,
            }
        )
    )
    SCORING_PIPELINE_LATENCY.observe(latency_ms)
    if gate_result.passed:
        LLM_BOOST_VALUE.observe(boost_value)
    # 8. SAVE TO CACHE
    if redis_client.redis:
        await redis_client.redis.set(cache_key, json.dumps(final_result), ex=CACHE_TTL)

    return final_result


async def match_programs(user_id: str) -> list[dict]:
    """Filtered, batch-scored, ranked top-N programs for one user.

    Replaces the previous fan-out, which scored EVERY row in program_requirements with
    two queries per program (profile + program) plus a Redis get/set each. That is
    ~40,000 round trips against the ~20,000-program European catalog. Here the profile
    is fetched once, candidates come back in a single query, and scoring is in memory.

    Filters are null-tolerant on purpose: a profile with no target countries or no
    recognised field of study must still get results, so an absent preference widens
    the search instead of emptying it.
    """
    cache_key = f"match:{user_id}"
    if redis_client.redis:
        cached = await redis_client.redis.get(cache_key)
        if cached:
            logger.info("Match cache hit", user_id=user_id)
            return json.loads(cached)

    user_data = await get_local_user_profile(user_id)
    if not user_data:
        raise HTTPException(status_code=425, detail="Profile not yet replicated. Please retry.")
    profile = UserProfile(**user_data)

    countries = profile.targetCountries or None
    discipline = discipline_for_field_of_study(profile.fieldOfStudy)

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, program_name, university, country, deadline, discipline,
                   degree_level, min_ects, min_gpa, min_ielts,
                   required_citizenship, min_work_experience
            FROM program_requirements
            WHERE ($1::text[] IS NULL OR country = ANY($1::text[]))
              AND ($2::text IS NULL OR discipline IS NULL OR discipline = $2::text)
            ORDER BY (deadline IS NULL), deadline, id
            LIMIT $3
            """,
            countries,
            discipline,
            MATCH_CANDIDATE_CAP,
        )

        # One finance lookup per distinct country, not per program (GOA-108).
        finance_by_country: dict[str, list[dict]] = {}
        for country in {r["country"] for r in rows if r["country"]}:
            finance_by_country[country] = await get_student_visa_finance(country, conn=conn)

    results = []
    for r in rows:
        program = ProgramRequirements(
            id=str(r["id"]),
            country=r["country"],
            degree_level=r["degree_level"],
            min_ects=r["min_ects"],
            min_gpa=float(r["min_gpa"]) if r["min_gpa"] is not None else None,
            min_ielts=float(r["min_ielts"]) if r["min_ielts"] is not None else None,
            required_citizenship=r["required_citizenship"],
            min_work_experience=r["min_work_experience"],
        )
        result = score_profile_against_program(
            profile, program, finance_by_country.get(r["country"])
        )
        results.append(
            {
                "programId": str(r["id"]),
                "programName": r["program_name"] or f"{r['university']} — {r['degree_level']}",
                "university": r["university"],
                "country": r["country"],
                "deadline": str(r["deadline"]) if r["deadline"] else None,
                "requirements": {
                    "minEcts": r["min_ects"],
                    "minGpa": float(r["min_gpa"]) if r["min_gpa"] is not None else None,
                    "minIelts": float(r["min_ielts"]) if r["min_ielts"] is not None else None,
                    "degreeLevel": r["degree_level"],
                    "minWorkExperience": r["min_work_experience"],
                },
                "result": result,
            }
        )

    results.sort(key=lambda x: x["result"]["score"], reverse=True)
    ranked = results[:MATCH_RESULT_LIMIT]

    logger.info(
        "match_completed",
        user_id=user_id,
        candidates=len(rows),
        returned=len(ranked),
        filtered_by_country=bool(countries),
        filtered_by_discipline=discipline,
    )

    if redis_client.redis:
        await redis_client.redis.set(cache_key, json.dumps(ranked), ex=CACHE_TTL)
    return ranked

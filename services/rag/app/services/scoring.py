import time
import json
import structlog
from fastapi import HTTPException
from langfuse import get_client, observe
from app.core.database import db
from app.core.config import settings
from app.core.redis import redis_client
from app.schemas.scoring import UserProfile, ProgramRequirements
from app.clients.writing_client import get_user_cv
from app.services.gates import check_hard_gates
from app.services.soft_score import (
    compute_score_breakdown,
    discipline_for_field_of_study,
    requirement_summary,
    subject_relevance,
)
from app.services.llm_boost import get_llm_boost
from app.services.gap_report import generate_gap_report
from app.services.visa_finance import get_student_visa_finance
from app.services.visa_service import get_visa_requirements_for_country
from app.core.metrics import SCORING_PIPELINE_LATENCY, LLM_BOOST_VALUE


logger = structlog.get_logger("rag_service.scoring")
# 1 Hour Cache TTL
CACHE_TTL = 3600
# Bump when response semantics change so deployments never serve an hour of
# pre-change percentages or omit newly added programme detail fields.
CACHE_SCHEMA_VERSION = "fit-v10-subject-dominant-calibration"

# Safety cap on how many programs one /match request will score after filtering.
# The catalog is ~20,000 in-scope European Engineering/CS programs; country and
# discipline filters normally cut that to tens, but an unfiltered profile (no target
# countries, no field of study) would otherwise score the whole table.
MATCH_CANDIDATE_CAP = 500

# How many ranked results /match returns. The scraped catalogue is large enough to
# support exploration; the previous top-10 cap made hundreds of records invisible.
MATCH_RESULT_LIMIT = 50


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
    score_breakdown = compute_score_breakdown(profile, program)
    requirements_evaluated, requirements_met = requirement_summary(profile, program)
    if not gate_result.passed:
        return {
            "score": score_breakdown["total"],
            "requirements_evaluated": requirements_evaluated,
            "requirements_met": requirements_met,
            "score_breakdown": score_breakdown,
            "blocked_by": gate_result.gateType,
            "gap_report": {gate_result.gateType: gate_result.reason},
        }

    gap_report = generate_gap_report(profile, program)
    if finance_items:
        gap_report["financial"] = finance_items

    return {
        "score": score_breakdown["total"],
        "requirements_evaluated": requirements_evaluated,
        "requirements_met": requirements_met,
        "score_breakdown": score_breakdown,
        "blocked_by": None,
        "gap_report": gap_report,
    }


async def get_local_user_profile(user_id: str) -> dict | None:
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id, ects, gpa, gpa_scale, ielts_score, degree_level, 
                   work_exp, extracurriculars, target_countries, field_of_study,
                   target_field_of_study
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
            "targetFieldOfStudy": row.get("target_field_of_study")
            or row["field_of_study"],
        }


async def get_program_requirements(program_id: str) -> ProgramRequirements | None:
    # RAG service uses raw asyncpg SQL
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, program_name, country, discipline, min_ects, degree_level,
                   required_citizenship, min_ielts, min_gpa, min_work_experience
            FROM program_requirements
            WHERE id = $1
        """,
            program_id,
        )

        if not row:
            return None

        return ProgramRequirements(
            id=str(row["id"]),
            name=row["program_name"],
            country=row["country"],
            discipline=row["discipline"],
            min_ects=row["min_ects"],
            degree_level=row["degree_level"],
            required_citizenship=row["required_citizenship"],
            min_ielts=row["min_ielts"],
            min_gpa=row["min_gpa"],
            min_work_experience=row["min_work_experience"],
        )


@observe(as_type="span", name="GOA-012-scoring-pipeline")
async def calculate_score(
    user_id: str, program_id: str, apply_llm_boost: bool = True
) -> dict:
    start_time = time.time()

    # CACHE-FIRST PRECEDENCE
    cache_key = (
        f"score:{user_id}:{program_id}:boost_{apply_llm_boost}:{CACHE_SCHEMA_VERSION}"
    )
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
    score_breakdown = compute_score_breakdown(profile, program)
    requirements_evaluated, requirements_met = requirement_summary(profile, program)

    if not gate_result.passed:
        final_result = {
            "score": score_breakdown["total"],
            "requirements_evaluated": requirements_evaluated,
            "requirements_met": requirements_met,
            "score_breakdown": score_breakdown,
            "blocked_by": gate_result.gateType,
            "gap_report": {gate_result.gateType: gate_result.reason},
        }
        soft_score = 0
        boost_value = 0
    else:
        # STAGE 2: SOFT SCORE
        soft_score = score_breakdown["total"]

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

        # CV feedback is explanatory only. It must not rewrite deterministic
        # admission evidence or preference alignment.
        final_score = soft_score

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
            "requirements_evaluated": requirements_evaluated,
            "requirements_met": requirements_met,
            "score_breakdown": score_breakdown,
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
    cache_key = f"match:{user_id}:{CACHE_SCHEMA_VERSION}"
    if redis_client.redis:
        cached = await redis_client.redis.get(cache_key)
        if cached:
            logger.info("Match cache hit", user_id=user_id)
            return json.loads(cached)

    user_data = await get_local_user_profile(user_id)
    if not user_data:
        raise HTTPException(
            status_code=425, detail="Profile not yet replicated. Please retry."
        )
    profile = UserProfile(**user_data)

    countries = profile.targetCountries or None
    target_field = profile.targetFieldOfStudy or profile.fieldOfStudy
    discipline = discipline_for_field_of_study(target_field)

    async with db.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, program_name, university, country, deadline, discipline, source_url, last_scraped_at,
                   degree_level, min_ects, min_gpa, min_ielts,
                   required_citizenship, min_work_experience
            FROM program_requirements
            WHERE ($1::text[] IS NULL OR country = ANY($1::text[]))
              AND ($2::text IS NULL OR discipline IS NULL OR discipline = $2::text)
              AND ($4::boolean OR source_url NOT LIKE 'https://goa.internal/seed/%')
              AND (deadline IS NULL OR deadline >= CURRENT_DATE)
            ORDER BY (deadline IS NULL), deadline, id
            LIMIT $3
            """,
            countries,
            discipline,
            MATCH_CANDIDATE_CAP,
            settings.include_demo_programs,
        )

        # One finance lookup per distinct country, not per program (GOA-108).
        finance_by_country: dict[str, list[dict]] = {}
        visa_by_country: dict[str, list[dict]] = {}
        for country in {r["country"] for r in rows if r["country"]}:
            finance_by_country[country] = await get_student_visa_finance(
                country, conn=conn
            )
            visa_by_country[country] = await get_visa_requirements_for_country(
                country, conn=conn
            )

    results = []
    for r in rows:
        program = ProgramRequirements(
            id=str(r["id"]),
            name=r["program_name"],
            country=r["country"],
            discipline=r["discipline"],
            degree_level=r["degree_level"],
            min_ects=r["min_ects"],
            min_gpa=float(r["min_gpa"]) if r["min_gpa"] is not None else None,
            min_ielts=float(r["min_ielts"]) if r["min_ielts"] is not None else None,
            required_citizenship=r["required_citizenship"],
            min_work_experience=r["min_work_experience"],
        )
        relevance = subject_relevance(target_field, program.name)
        # When the intended subject is classifiable, a zero means the title is
        # genuinely unrelated. Do not let academic surplus resurrect it as a
        # 98% "fit" merely because ingestion found it in a broad search bucket.
        if relevance == 0.0:
            continue
        result = score_profile_against_program(
            profile, program, finance_by_country.get(r["country"])
        )
        results.append(
            {
                "programId": str(r["id"]),
                "programName": r["program_name"]
                or f"{r['university']} — {r['degree_level']}",
                "university": r["university"],
                "country": r["country"],
                "deadline": str(r["deadline"]) if r["deadline"] else None,
                "sourceUrl": r.get("source_url"),
                "dataSource": "demo"
                if str(r.get("source_url") or "").startswith(
                    "https://goa.internal/seed/"
                )
                else "scraped",
                "lastScrapedAt": r.get("last_scraped_at").isoformat()
                if r.get("last_scraped_at")
                else None,
                "discipline": r["discipline"],
                "visaRequirements": visa_by_country.get(r["country"], []),
                "requirements": {
                    "minEcts": r["min_ects"],
                    "minGpa": float(r["min_gpa"]) if r["min_gpa"] is not None else None,
                    "minIelts": float(r["min_ielts"])
                    if r["min_ielts"] is not None
                    else None,
                    "degreeLevel": r["degree_level"],
                    "minWorkExperience": r["min_work_experience"],
                    "requiredCitizenship": r["required_citizenship"],
                },
                "result": result,
            }
        )

    results.sort(
        key=lambda x: (
            x["result"].get("blocked_by") is not None,
            -(x["result"].get("score_breakdown", {}).get("subject_relevance") or 0.0),
            -x["result"]["score"],
            -x["result"].get("requirements_evaluated", 0),
            x["deadline"] is None,
            x["deadline"] or "9999-12-31",
            x["programName"].lower(),
        )
    )
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


async def get_program_detail(user_id: str, program_id: str) -> dict:
    """Return one programme's complete structured record and personalised fit."""
    user_data = await get_local_user_profile(user_id)
    if not user_data:
        raise HTTPException(
            status_code=425, detail="Profile not yet replicated. Please retry."
        )
    profile = UserProfile(**user_data)

    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, program_name, university, country, deadline, discipline,
                   source_url, degree_level, min_ects, min_gpa, min_ielts,
                   required_citizenship, min_work_experience, last_scraped_at,
                   updated_at
            FROM program_requirements
            WHERE id = $1
            """,
            program_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Program not found")
        visa = (
            await get_visa_requirements_for_country(row["country"], conn=conn)
            if row["country"]
            else []
        )
        finance = (
            await get_student_visa_finance(row["country"], conn=conn)
            if row["country"]
            else []
        )

    program = ProgramRequirements(
        id=str(row["id"]),
        name=row["program_name"],
        country=row["country"],
        discipline=row["discipline"],
        degree_level=row["degree_level"],
        min_ects=row["min_ects"],
        min_gpa=float(row["min_gpa"]) if row["min_gpa"] is not None else None,
        min_ielts=float(row["min_ielts"]) if row["min_ielts"] is not None else None,
        required_citizenship=row["required_citizenship"],
        min_work_experience=row["min_work_experience"],
    )
    return {
        "programId": str(row["id"]),
        "programName": row["program_name"]
        or f"{row['university']} — {row['degree_level']}",
        "university": row["university"],
        "country": row["country"],
        "deadline": str(row["deadline"]) if row["deadline"] else None,
        "sourceUrl": row["source_url"],
        "discipline": row["discipline"],
        "lastScrapedAt": row["last_scraped_at"].isoformat()
        if row["last_scraped_at"]
        else None,
        "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
        "visaRequirements": visa,
        "requirements": {
            "minEcts": row["min_ects"],
            "minGpa": float(row["min_gpa"]) if row["min_gpa"] is not None else None,
            "minIelts": float(row["min_ielts"])
            if row["min_ielts"] is not None
            else None,
            "degreeLevel": row["degree_level"],
            "minWorkExperience": row["min_work_experience"],
            "requiredCitizenship": row["required_citizenship"],
        },
        "result": score_profile_against_program(profile, program, finance),
    }

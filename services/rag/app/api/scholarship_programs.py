from fastapi import APIRouter, HTTPException, Security
import structlog

from app.core.database import db
from app.core.security import verify_api_key
from app.schemas.scholarship_programs import ScholarshipProgramUpsertRequest
from app.services.scholarship_programs_service import upsert_scholarship_program

router = APIRouter()
logger = structlog.get_logger("rag_service.api.scholarship_programs")

@router.post("/internal/scholarship-programs")
async def handle_scholarship_programs(request: ScholarshipProgramUpsertRequest, _ = Security(verify_api_key)):
    try:
        data = request.model_dump()
        result = await upsert_scholarship_program(data)
        return result
    except Exception as e:
        logger.error("Scholarship program processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")


@router.get("/internal/scholarship-programs/updated")
async def list_updated_scholarships(
    since_hours: int = 24,
    deadline_within_days: int | None = None,
    _=Security(verify_api_key),
):
    """Scholarships changed recently, for GOA-024's daily matcher.

    The Ingestion service must never read RAG's tables directly (GOA-024), so the
    matcher pulls its candidates through here. `deadline_within_days` additionally
    returns rows whose deadline is imminent, which is what drives DEADLINE_REMINDER
    events — a scholarship can be unchanged for weeks and still become urgent.
    """
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, provider, country, degree_level, award_amount,
                       deadline, citizenship_eligible, min_gpa, min_ielts, updated_at
                FROM scholarship_programs
                WHERE updated_at >= now() - ($1 || ' hours')::interval
                   OR ($2::int IS NOT NULL
                       AND deadline IS NOT NULL
                       AND deadline BETWEEN CURRENT_DATE
                                        AND CURRENT_DATE + ($2 || ' days')::interval)
                ORDER BY deadline NULLS LAST, name
                """,
                str(since_hours),
                deadline_within_days,
            )
        return {
            "scholarships": [
                {
                    # UUID and Decimal are not JSON-serialisable; coercing here rather
                    # than at the caller matches the fix applied to /internal/visa-sources.
                    "id": str(r["id"]),
                    "name": r["name"],
                    "provider": r["provider"],
                    "country": r["country"],
                    "degree_level": r["degree_level"],
                    "award_amount": r["award_amount"],
                    "deadline": r["deadline"].isoformat() if r["deadline"] else None,
                    "citizenship_eligible": r["citizenship_eligible"],
                    "min_gpa": float(r["min_gpa"]) if r["min_gpa"] is not None else None,
                    "min_ielts": float(r["min_ielts"]) if r["min_ielts"] is not None else None,
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Updated scholarship lookup failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")


@router.get("/internal/profiles/by-country")
async def list_profiles_by_country(country: str, _=Security(verify_api_key)):
    """Profiles targeting a country, fetched in bulk for the matcher.

    Deliberately one query returning every candidate profile rather than a per-user
    lookup: GOA-024 scores every matching user against every updated scholarship, and
    a per-user round trip is the fan-out pathology that made /match unusable at
    catalog scale (see match_programs).
    """
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, ects, gpa, gpa_scale, ielts_score, degree_level,
                       work_exp, extracurriculars, target_countries, field_of_study
                FROM local_user_profiles
                WHERE $1 = ANY(target_countries)
                """,
                country,
            )
        return {
            "profiles": [
                {
                    "userId": str(r["user_id"]),
                    "ects": r["ects"],
                    "gpa": float(r["gpa"]) if r["gpa"] is not None else None,
                    "gpaScale": r["gpa_scale"],
                    "ieltsScore": float(r["ielts_score"]) if r["ielts_score"] is not None else None,
                    "degreeLevel": r["degree_level"],
                    "workExperienceYears": r["work_exp"] or 0,
                    "extracurricularsScore": r["extracurriculars"] or 0,
                    "targetCountries": r["target_countries"] or [],
                    "fieldOfStudy": r["field_of_study"],
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Profile lookup by country failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Processing Error")

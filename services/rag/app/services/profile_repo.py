import structlog
from app.core.database import db

logger = structlog.get_logger("rag_service.profile_repo")


async def upsert_local_profiles(profile_dict: dict) -> None:
    """
    Upserts a user profile into the local_user_profiles table.
    Expects the User service's camelCase event payload and maps it to snake_case.
    """

    try:
        user_id = profile_dict["userId"]
        ects = profile_dict["ects"]
        gpa = profile_dict["gpa"]
        gpa_scale = profile_dict["gpaScale"]
        ielts_score = profile_dict["ieltsScore"]
        degree_level = profile_dict["degreeLevel"]
        work_exp = profile_dict["workExperienceYears"]
        extracurriculars = profile_dict["extracurricularsScore"]

        # JSONB column needs to be passed as a string or parsed depending on asyncpg setup.
        # We will dump the list/dict into a JSON string for asyncpg's parameter binding.

        target_countries = profile_dict.get("targetCountries", [])
        last_synced_at = profile_dict.get("last_synced_at")

        query = """
            INSERT INTO local_user_profiles (
                user_id, ects, gpa, gpa_scale, ielts_score, degree_level,
                work_exp, extracurriculars, target_countries, last_synced_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
            )
            ON CONFLICT (user_id) DO UPDATE SET
                ects = EXCLUDED.ects,
                gpa = EXCLUDED.gpa,
                gpa_scale = EXCLUDED.gpa_scale,
                ielts_score = EXCLUDED.ielts_score,
                degree_level = EXCLUDED.degree_level,
                work_exp = EXCLUDED.work_exp,
                extracurriculars = EXCLUDED.extracurriculars,
                target_countries = EXCLUDED.target_countries,
                last_synced_at = EXCLUDED.last_synced_at,
                updated_at = CURRENT_TIMESTAMP
            WHERE local_user_profiles.last_synced_at IS NULL 
               OR local_user_profiles.last_synced_at < EXCLUDED.last_synced_at;
        """

        async with db.pool.acquire() as conn:
            await conn.execute(
                query,
                user_id,
                ects,
                gpa,
                gpa_scale,
                ielts_score,
                degree_level,
                work_exp,
                extracurriculars,
                target_countries,
                last_synced_at,
            )

        logger.debug("Successfully upserted local profile", user_id=user_id)

    except KeyError as e:
        logger.error(
            "Missing expected field in profile payload",
            missing_field=str(e),
            user_id=profile_dict["userId"],
        )
        raise
    except Exception as e:
        logger.error(
            "Failed to upsert local profile",
            error=str(e),
            user_id=profile_dict["userId"],
        )
        raise

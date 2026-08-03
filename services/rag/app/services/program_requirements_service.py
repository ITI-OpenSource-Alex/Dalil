from typing import Any, Dict

from app.core.database import db


async def upsert_program_requirements(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a structured program requirements record, keyed by canonical source_url.

    Uses a single atomic INSERT ... ON CONFLICT (source_url) DO UPDATE statement
    so concurrent upserts for the same program page never race.
    """
    university = data["university"]
    country = data["country"]
    degree_level = data["degree_level"]
    source_url = data["source_url"]

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO program_requirements (
                    university, country, degree_level, program_name, deadline, min_ects, min_gpa, min_ielts,
                    required_citizenship, min_work_experience, source_url, content_hash, discipline,
                    last_scraped_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW(), NOW())
                ON CONFLICT (source_url) DO UPDATE
                SET university = EXCLUDED.university,
                    country = EXCLUDED.country,
                    degree_level = EXCLUDED.degree_level,
                    program_name = EXCLUDED.program_name,
                    deadline = EXCLUDED.deadline,
                    min_ects = EXCLUDED.min_ects,
                    min_gpa = EXCLUDED.min_gpa,
                    min_ielts = EXCLUDED.min_ielts,
                    required_citizenship = EXCLUDED.required_citizenship,
                    min_work_experience = EXCLUDED.min_work_experience,
                    content_hash = EXCLUDED.content_hash,
                    discipline = COALESCE(EXCLUDED.discipline, program_requirements.discipline),
                    last_scraped_at = NOW(),
                    updated_at = NOW()
                RETURNING id, (xmax = 0) AS inserted
                """,
                university,
                country,
                degree_level,
                data.get("program_name"),
                data.get("deadline"),
                data.get("min_ects"),
                data.get("min_gpa"),
                data.get("min_ielts"),
                data.get("required_citizenship"),
                data.get("min_work_experience"),
                source_url,
                data.get("content_hash"),
                data.get("discipline"),
            )

            action = "inserted" if row["inserted"] else "updated"
            return {"status": "success", "id": str(row["id"]), "action": action}

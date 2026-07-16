from typing import Any, Dict

from app.core.database import db


async def upsert_program_requirements(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a structured program requirements record, keyed by
    (university, degree_level, country).

    Uses a single atomic INSERT ... ON CONFLICT DO UPDATE statement so concurrent
    upserts for the same key can never race, mirroring visa_service.upsert_visa_requirements.

    Unlike the visa upsert, this always rewrites the mutable fields and last_scraped_at
    on conflict rather than skipping when content_hash is unchanged -- GOA-088 requires
    last_scraped_at to advance on every re-ingestion of the same source, even when the
    content itself hasn't changed.
    """
    university = data["university"]
    country = data["country"]
    degree_level = data["degree_level"]

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO program_requirements (
                    university, country, degree_level, min_ects, min_gpa, min_ielts,
                    required_citizenship, min_work_experience, source_url, content_hash,
                    last_scraped_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW())
                ON CONFLICT (university, degree_level, country) DO UPDATE
                SET min_ects = EXCLUDED.min_ects,
                    min_gpa = EXCLUDED.min_gpa,
                    min_ielts = EXCLUDED.min_ielts,
                    required_citizenship = EXCLUDED.required_citizenship,
                    min_work_experience = EXCLUDED.min_work_experience,
                    source_url = EXCLUDED.source_url,
                    content_hash = EXCLUDED.content_hash,
                    last_scraped_at = NOW(),
                    updated_at = NOW()
                RETURNING id, (xmax = 0) AS inserted
                """,
                university,
                country,
                degree_level,
                data.get("min_ects"),
                data.get("min_gpa"),
                data.get("min_ielts"),
                data.get("required_citizenship"),
                data.get("min_work_experience"),
                data.get("source_url"),
                data.get("content_hash"),
            )

            action = "inserted" if row["inserted"] else "updated"
            return {"status": "success", "id": str(row["id"]), "action": action}

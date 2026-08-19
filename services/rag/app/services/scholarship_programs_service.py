import json
from typing import Any, Dict

from app.core.database import db


async def upsert_scholarship_program(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a structured scholarship program record, keyed by (provider, name).

    Uses a single atomic INSERT ... ON CONFLICT DO UPDATE statement, mirroring
    visa_service.upsert_visa_requirements. Like program_requirements_service, this
    always rewrites mutable fields and last_scraped_at on conflict -- GOA-088 requires
    last_scraped_at to advance on every re-ingestion, even when content is unchanged.
    """
    provider = data["provider"]
    name = data["name"]

    eligibility_json = json.dumps(data.get("eligibility") or {})

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO scholarship_programs (
                    name, provider, country, degree_level, award_amount, deadline,
                    eligibility, citizenship_eligible, min_gpa, min_ielts, source_url,
                    content_hash, last_scraped_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12, NOW(), NOW())
                ON CONFLICT (provider, name) DO UPDATE
                SET country = EXCLUDED.country,
                    degree_level = EXCLUDED.degree_level,
                    award_amount = EXCLUDED.award_amount,
                    deadline = EXCLUDED.deadline,
                    eligibility = EXCLUDED.eligibility,
                    citizenship_eligible = EXCLUDED.citizenship_eligible,
                    min_gpa = EXCLUDED.min_gpa,
                    min_ielts = EXCLUDED.min_ielts,
                    source_url = EXCLUDED.source_url,
                    content_hash = EXCLUDED.content_hash,
                    last_scraped_at = NOW(),
                    updated_at = NOW()
                RETURNING id, (xmax = 0) AS inserted
                """,
                name,
                provider,
                data.get("country"),
                data.get("degree_level"),
                data.get("award_amount"),
                data.get("deadline"),
                eligibility_json,
                data.get("citizenship_eligible", True),
                data.get("min_gpa"),
                data.get("min_ielts"),
                data["source_url"],
                data.get("content_hash"),
            )

            action = "inserted" if row["inserted"] else "updated"
            return {"status": "success", "id": str(row["id"]), "action": action}

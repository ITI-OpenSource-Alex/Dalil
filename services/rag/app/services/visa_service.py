import json
from typing import Any, Dict

from app.core.database import db


async def upsert_visa_requirements(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a structured visa requirements record, keyed by (country, visa_type, issuing_body).

    Uses a single atomic INSERT ... ON CONFLICT DO UPDATE statement so concurrent
    upserts for the same key can never race (a prior SELECT-then-branch implementation
    was vulnerable to a TOCTOU unique-constraint violation under concurrent requests).
    Skips rewriting mutable fields and last_scraped_at when the incoming content_hash
    matches the stored value, to avoid needless churn on unchanged source content.
    """
    country = data["country"]
    visa_type = data["visa_type"]
    issuing_body = data["issuing_body"]
    incoming_content_hash = data.get("content_hash")

    requirements_json = json.dumps(data.get("requirements") or {})
    proof_of_funds = data.get("proof_of_funds")
    proof_of_funds_json = json.dumps(proof_of_funds) if proof_of_funds is not None else None

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO visa_requirements (
                    country, visa_type, issuing_body, source_url, egyptian_specific,
                    requirements, proof_of_funds, processing_days_min, processing_days_max,
                    notes, content_hash, last_scraped_at
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11, NOW())
                ON CONFLICT (country, visa_type, issuing_body) DO UPDATE
                SET source_url = EXCLUDED.source_url,
                    egyptian_specific = EXCLUDED.egyptian_specific,
                    requirements = EXCLUDED.requirements,
                    proof_of_funds = EXCLUDED.proof_of_funds,
                    processing_days_min = EXCLUDED.processing_days_min,
                    processing_days_max = EXCLUDED.processing_days_max,
                    notes = EXCLUDED.notes,
                    content_hash = EXCLUDED.content_hash,
                    last_scraped_at = NOW()
                WHERE visa_requirements.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                RETURNING id, (xmax = 0) AS inserted
                """,
                country,
                visa_type,
                issuing_body,
                data.get("source_url"),
                data["egyptian_specific"],
                requirements_json,
                proof_of_funds_json,
                data.get("processing_days_min"),
                data.get("processing_days_max"),
                data.get("notes"),
                incoming_content_hash,
            )

            if row is not None:
                action = "inserted" if row["inserted"] else "updated"
                return {"status": "success", "id": str(row["id"]), "action": action}

            # The WHERE clause suppressed the update because content_hash was
            # unchanged, so ON CONFLICT DO UPDATE returned no row -- look up the
            # existing row's id for the response.
            existing = await conn.fetchrow(
                "SELECT id FROM visa_requirements WHERE country = $1 AND visa_type = $2 AND issuing_body = $3",
                country, visa_type, issuing_body,
            )
            return {"status": "success", "id": str(existing["id"]), "action": "unchanged"}

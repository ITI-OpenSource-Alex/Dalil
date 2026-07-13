import json
from typing import Any, Dict

from app.core.database import db


async def upsert_visa_requirements(data: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert a structured visa requirements record, keyed by (country, visa_type, issuing_body).

    Skips rewriting mutable fields and last_scraped_at when the incoming content_hash matches
    the stored value, to avoid needless churn on unchanged source content.
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
            existing = await conn.fetchrow(
                """
                SELECT id, content_hash
                FROM visa_requirements
                WHERE country = $1 AND visa_type = $2 AND issuing_body = $3
                """,
                country, visa_type, issuing_body
            )

            if existing is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO visa_requirements (
                        country, visa_type, issuing_body, source_url, egyptian_specific,
                        requirements, proof_of_funds, processing_days_min, processing_days_max,
                        notes, content_hash, last_scraped_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11, NOW())
                    RETURNING id
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
                return {"status": "success", "id": str(row["id"]), "action": "inserted"}

            if existing["content_hash"] == incoming_content_hash:
                return {"status": "success", "id": str(existing["id"]), "action": "unchanged"}

            await conn.execute(
                """
                UPDATE visa_requirements
                SET source_url = $1,
                    egyptian_specific = $2,
                    requirements = $3::jsonb,
                    proof_of_funds = $4::jsonb,
                    processing_days_min = $5,
                    processing_days_max = $6,
                    notes = $7,
                    content_hash = $8,
                    last_scraped_at = NOW()
                WHERE id = $9
                """,
                data.get("source_url"),
                data["egyptian_specific"],
                requirements_json,
                proof_of_funds_json,
                data.get("processing_days_min"),
                data.get("processing_days_max"),
                data.get("notes"),
                incoming_content_hash,
                existing["id"],
            )
            return {"status": "success", "id": str(existing["id"]), "action": "updated"}

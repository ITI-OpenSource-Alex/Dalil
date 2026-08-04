import json

import structlog
from fastapi import APIRouter, HTTPException, Security

from app.core.database import db
from app.core.security import verify_api_key
from app.schemas.faq import FAQUpsertRequest, FAQUpsertResponse

router = APIRouter()
logger = structlog.get_logger("rag_service.api.faq")


@router.post("/internal/faq", response_model=FAQUpsertResponse, status_code=200)
async def upsert_faq_entry(
    request: FAQUpsertRequest, _=Security(verify_api_key)
) -> FAQUpsertResponse:
    """GOA-045: add or update one curated FAQ entry.

    Upsert on question_pattern rather than insert: curating is iterative, and an
    endpoint that appends on every call quietly fills the table with near-
    duplicates that then compete with each other for the same fuzzy match.

    Editing an entry counts as reviewing it, so an omitted reviewed_at means
    now. That is deliberate -- the alternative is an edited answer that inherits
    an old review date and expires sooner than the person editing it expects.
    """
    reviewed_at = request.reviewed_at
    sources_json = json.dumps([s.model_dump() for s in request.sources])

    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO faq_entries (
                    question_pattern, answer_markdown, sources, category,
                    source_url, reviewed_at, review_interval_days
                )
                VALUES ($1, $2, $3::jsonb, $4, $5, COALESCE($6, NOW()), $7)
                ON CONFLICT (question_pattern) DO UPDATE SET
                    answer_markdown      = EXCLUDED.answer_markdown,
                    sources              = EXCLUDED.sources,
                    category             = EXCLUDED.category,
                    source_url           = EXCLUDED.source_url,
                    reviewed_at          = EXCLUDED.reviewed_at,
                    review_interval_days = EXCLUDED.review_interval_days,
                    last_updated         = NOW()
                RETURNING id, question_pattern, category, source_url,
                          reviewed_at, review_interval_days,
                          (xmax = 0) AS created
                """,
                request.question_pattern,
                request.answer_markdown,
                sources_json,
                request.category,
                request.source_url,
                reviewed_at,
                request.review_interval_days,
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("faq_upsert_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to upsert FAQ entry")

    logger.info(
        "faq_upserted",
        faq_id=str(row["id"]),
        created=row["created"],
        category=row["category"],
    )

    return FAQUpsertResponse(
        id=str(row["id"]),
        question_pattern=row["question_pattern"],
        category=row["category"],
        source_url=row["source_url"],
        reviewed_at=row["reviewed_at"],
        review_interval_days=row["review_interval_days"],
        created=row["created"],
    )

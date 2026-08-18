"""Motivation letter review endpoints.

Synchronous on purpose. The CV pipeline is queue-driven and that indirection is the
single hardest part of it to demonstrate or debug -- an upload returns 202 and the
result appears somewhere else, later, if the worker is healthy. A letter review is a
foreground action the student is waiting on, so it returns the result directly and
fails visibly.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.dependencies import get_db
from app.models import MotivationLetter
from app.motivation_agents import review_letter
from app.schemas import (
    MotivationLetterCreateRequest,
    MotivationLetterResponse,
    MotivationLetterSummary,
)

router = APIRouter(prefix="/motivation-letters", tags=["motivation-letters"])
logger = logging.getLogger("writing_service.motivation_letters")

MIN_WORDS = 100
MAX_CHARS = 20000


def _to_response(row: MotivationLetter) -> MotivationLetterResponse:
    return MotivationLetterResponse(
        letterId=row.id,
        userId=row.user_id,
        programId=row.program_id,
        status=row.status,
        overallScore=float(row.overall_score) if row.overall_score is not None else None,
        criteria=row.criteria or [],
        programmeSnapshot=row.programme_snapshot,
        content=row.content,
        errorMessage=row.error_message,
        createdAt=row.created_at.isoformat() if row.created_at else None,
        completedAt=row.completed_at.isoformat() if row.completed_at else None,
    )


async def _fetch_programme(
    program_id: str | None, settings: Settings
) -> dict[str, Any] | None:
    """Read programme requirements from RAG, which owns them.

    Returns None on any failure. A missing programme must not fail the review: the
    programme_fit criterion abstains and the other four still run. Blocking the whole
    feature on a catalogue lookup would make it fail exactly when the corpus is thin,
    which is precisely when a student still wants feedback on their letter.
    """
    if not program_id:
        return None
    url = f"{settings.rag_service_url.rstrip('/')}/internal/programs/{program_id}/requirements"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url, headers={"X-Internal-Api-Key": settings.internal_api_key}
            )
            if response.status_code != 200:
                logger.warning(
                    "Programme lookup returned %s for %s", response.status_code, program_id
                )
                return None
            return response.json()
    except Exception:
        logger.exception("Programme lookup failed for %s", program_id)
        return None


@router.post("", response_model=MotivationLetterResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    payload: MotivationLetterCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MotivationLetterResponse:
    content = (payload.content or "").strip()
    if len(content) > MAX_CHARS:
        raise HTTPException(status_code=413, detail="Letter exceeds 20,000 characters")
    if len(content.split()) < MIN_WORDS:
        raise HTTPException(
            status_code=422,
            detail=f"A motivation letter needs at least {MIN_WORDS} words to review",
        )

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Re-submitting identical text for the same programme returns the stored review
    # rather than paying for five more model calls.
    existing = (
        db.query(MotivationLetter)
        .filter(
            MotivationLetter.user_id == payload.userId,
            MotivationLetter.program_id == payload.programId,
            MotivationLetter.content_hash == content_hash,
            MotivationLetter.status == "completed",
        )
        .order_by(MotivationLetter.id.desc())
        .first()
    )
    if existing:
        return _to_response(existing)

    row = MotivationLetter(
        user_id=payload.userId,
        program_id=payload.programId,
        content=content,
        content_hash=content_hash,
        status="processing",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    programme = await _fetch_programme(payload.programId, settings)
    try:
        criteria, overall = await review_letter(content, programme)
    except Exception as exc:
        logger.exception("Motivation letter review failed for letter %s", row.id)
        row.status = "failed"
        row.error_message = f"{type(exc).__name__}: {exc}"[:500]
        db.commit()
        db.refresh(row)
        raise HTTPException(status_code=502, detail="Review failed") from exc

    completed = [c for c in criteria if c.get("status") == "complete"]
    row.criteria = criteria
    row.overall_score = overall
    row.programme_snapshot = programme
    # "partial" is a real outcome, not a failure: some criteria abstained or errored
    # but the review still carries usable feedback. The UI labels it as such rather
    # than presenting a mean of two criteria as an overall judgement.
    row.status = "completed" if len(completed) == len(criteria) else "partial"
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.get("/{letter_id}", response_model=MotivationLetterResponse)
def get_review(
    letter_id: int,
    userId: str = Query(...),
    db: Session = Depends(get_db),
) -> MotivationLetterResponse:
    row = (
        db.query(MotivationLetter)
        .filter(MotivationLetter.id == letter_id, MotivationLetter.user_id == userId)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Motivation letter not found")
    return _to_response(row)


@router.get("", response_model=list[MotivationLetterSummary])
def list_reviews(
    userId: str = Query(...),
    programId: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[MotivationLetterSummary]:
    query = db.query(MotivationLetter).filter(MotivationLetter.user_id == userId)
    if programId:
        query = query.filter(MotivationLetter.program_id == programId)
    rows = query.order_by(MotivationLetter.id.desc()).limit(20).all()
    return [
        MotivationLetterSummary(
            letterId=r.id,
            programId=r.program_id,
            status=r.status,
            overallScore=float(r.overall_score) if r.overall_score is not None else None,
            createdAt=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]

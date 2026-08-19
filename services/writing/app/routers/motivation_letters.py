"""Motivation letter review endpoints.

Asynchronous, in-process. Submission returns 202 with a row at status='processing'
and the client polls for the result.

This began synchronous, on the reasoning that a letter review is a foreground action
and the CV pipeline's SQS hop is the hardest part of that feature to demo or debug.
Measurement overturned it: a real review took 2m32s, and an HTTP request held open
that long loses its result to any navigation, reload or dropped connection while the
server carries on computing it. The client had no way to rejoin work already running.

The middle position is the one taken here -- background execution for the duration,
without a broker. FastAPI BackgroundTasks keeps the work in this process, so a
restart mid-review abandons the row at 'processing'; the client bounds that by
treating a row stuck there past six minutes as stalled. A queue would fix it
properly, at the cost of the indirection the CV pipeline already demonstrates.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
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


async def _run_review(letter_id: int, content: str, program_id: str | None) -> None:
    """Run the five criterion agents and record the outcome.

    Owns its own Session. The request-scoped one from Depends(get_db) is closed the
    moment the 202 is returned, and this coroutine outlives that by minutes.

    Never raises: a background task has no caller to report to, so every failure is
    written to the row instead. A review that dies silently would leave the row at
    'processing' forever, which the client can only interpret as a stall.
    """
    db = SessionLocal()
    try:
        row = db.query(MotivationLetter).filter(MotivationLetter.id == letter_id).first()
        if row is None:
            logger.error("Motivation letter %s vanished before review", letter_id)
            return
        try:
            programme = await _fetch_programme(program_id, get_settings())
            criteria, overall = await review_letter(content, programme)
        except Exception as exc:
            logger.exception("Motivation letter review failed for letter %s", letter_id)
            row.status = "failed"
            row.error_message = f"{type(exc).__name__}: {exc}"[:500]
            row.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        completed = [c for c in criteria if c.get("status") == "complete"]
        row.criteria = criteria
        row.overall_score = overall
        row.programme_snapshot = programme
        # "partial" is a real outcome, not a failure: some criteria abstained or
        # errored but the review still carries usable feedback. The UI labels it as
        # such rather than presenting a mean of two criteria as an overall judgement.
        row.status = "completed" if len(completed) == len(criteria) else "partial"
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@router.post(
    "", response_model=MotivationLetterResponse, status_code=status.HTTP_202_ACCEPTED
)
async def create_review(
    payload: MotivationLetterCreateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MotivationLetterResponse:
    """Accept the letter, return immediately, review in the background.

    This was synchronous until a measured run took 2m32s. Holding an HTTP request
    open that long means any navigation, reload or flaky connection loses the result
    for the client while the server carries on producing it -- the client had no way
    to rejoin work that was already running.

    Returns 202 with the row at status='processing'; the client polls
    GET /motivation-letters/{id}. Same shape as the CV pipeline without the SQS hop:
    the queue there buys retries and cross-process durability that a foreground
    review does not need, at the cost of being the hardest part of that feature to
    demo or debug.

    Known limitation: BackgroundTasks runs in this process, so a restart mid-review
    abandons the row at 'processing'. The client treats a row stuck there past six
    minutes as stalled and re-enables submission, which bounds the damage without
    introducing a broker.
    """
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

    # Rejoin a review of this same letter that is already running, rather than
    # starting a second one. Without this, a double click or a resubmit from another
    # tab pays for five more model calls and races to write the same row.
    running = (
        db.query(MotivationLetter)
        .filter(
            MotivationLetter.user_id == payload.userId,
            MotivationLetter.program_id == payload.programId,
            MotivationLetter.content_hash == content_hash,
            MotivationLetter.status == "processing",
        )
        .order_by(MotivationLetter.id.desc())
        .first()
    )
    if running:
        return _to_response(running)

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

    background.add_task(_run_review, row.id, content, payload.programId)
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

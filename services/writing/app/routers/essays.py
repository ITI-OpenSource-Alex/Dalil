import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.schemas import EssayCreateRequest, EssayCreateResponse
from app.config import Settings, get_settings
from app.dependencies import get_db
from app.evaluation import (
    EvaluationCoordinator,
    EvaluationFailed,
    EvaluationSummary,
    get_evaluation_coordinator,
)
from app.metrics import EVALUATION_LATENCY_MS, cache_hit_tracker
from app.models import Essay
from app.observability import (
    get_langfuse_client,
    log_evaluation,
    start_evaluation_trace,
)
from app.schemas import EssayEvaluationRequest, EssayEvaluationResponse
from app.services.evaluation_store import (
    evaluation_cache_key,
    find_cached_evaluation,
    parse_cached_evaluations,
    persist_evaluation,
)

from app.schemas import (
    EssayEvaluationRequest,
    EssayEvaluationResponse,
    ExamTaskEvaluationRequest,
    ExamTaskEvaluationResponse,
)


router = APIRouter(prefix="/essays", tags=["essays"])

# TODO (GOA-112): Add `POST ""` on the existing `/essays`-prefixed router (i.e., bare `POST /essays`), returning 201.
# - Persist an Essay with status='ready' and return its id. 
# - Constraint: the returned id must be immediately usable by the existing POST /essays/{id}/evaluate SSE route with no extra setup — that means extracted_text, submission_type, and exam_type must be populated the same way /essays/evaluate populates them, or the SSE route's cache-key derivation will diverge for created-then-evaluated essays vs directly-evaluated ones.
# - Check whether the Essay model has an exam_session_id column. If not: nullable column + migration, following this service's existing migration numbering. Do not silently drop the field — GOA-053's exam mode will need it.

@router.post('', response_model=EssayCreateResponse, status_code=201)
async def create_essay(
    payload: EssayCreateRequest,
    db: Session = Depends(get_db),
):
    essay = Essay(
        user_id=payload.userId,
        extracted_text=payload.essayText,
        submission_type=payload.submissionType,
        exam_type=payload.submissionType,  # Aligns exactly with how /evaluate derives task_type
        exam_session_id=payload.examSessionId,
        status="ready",
    )

    db.add(essay)
    db.commit()
    db.refresh(essay)

    return EssayCreateResponse(
        id=essay.id,
        status=essay.status,
    )


def _response(
    essay: Essay, summary: EvaluationSummary, *, from_cache: bool
) -> EssayEvaluationResponse:
    return EssayEvaluationResponse(
        essay_id=essay.id,
        evaluations=summary.evaluations,
        overall_band=summary.overall_band,
        from_cache=from_cache,
    )

def _exam_response(
    essay: Essay,
    summary: EvaluationSummary,
    *,
    exam_session_id: str,
    task_number: int,
    from_cache: bool,
) -> ExamTaskEvaluationResponse:
    return ExamTaskEvaluationResponse(
        essay_id=essay.id,
        exam_session_id=exam_session_id,
        task_number=task_number,
        evaluations=summary.evaluations,
        overall_band=summary.overall_band,
        from_cache=from_cache,
    )

def _record_request(
    essay: Essay,
    summary: EvaluationSummary,
    *,
    started: float,
    from_cache: bool,
) -> None:
    latency_ms = (time.perf_counter() - started) * 1000
    EVALUATION_LATENCY_MS.observe(latency_ms)
    cache_hit_tracker.record(hit=from_cache)
    log_evaluation(
        user_id=essay.user_id,
        essay_id=essay.id,
        bands={item.criterion: item.band_score for item in summary.evaluations},
        overall_band=summary.overall_band,
        latency_ms=latency_ms,
        from_cache=from_cache,
        total_tokens=summary.total_tokens,
        total_cost_usd=summary.total_cost_usd,
    )


async def _run_evaluation(
    essay: Essay,
    *,
    cached_payload: dict | None,
    coordinator: EvaluationCoordinator,
    trace: Any,
    on_partial=None,
) -> EvaluationSummary:
    if cached_payload is not None:
        return await coordinator.replay_cached(
            parse_cached_evaluations(cached_payload),
            trace=trace,
            on_partial=on_partial,
        )
    return await coordinator.evaluate(
        essay.extracted_text,
        essay.exam_type or essay.submission_type or "IELTS Writing",
        trace=trace,
        on_partial=on_partial,
    )


@router.post("/evaluate", response_model=EssayEvaluationResponse)
async def evaluate_submitted_text(
    payload: EssayEvaluationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    coordinator: EvaluationCoordinator = Depends(get_evaluation_coordinator),
    langfuse_client: Any = Depends(get_langfuse_client),
):
    started = time.perf_counter()
    cache_key = evaluation_cache_key(
        payload.essayText,
        payload.submissionType,
        payload.examType,
        settings,
    )
    cached_payload = find_cached_evaluation(db, cache_key)
    essay = Essay(
        user_id=payload.userId,
        extracted_text=payload.essayText,
        submission_type=payload.submissionType,
        exam_type=payload.examType,
        evaluation_cache_key=cache_key,
        status="evaluating",
    )
    db.add(essay)
    db.commit()
    db.refresh(essay)
    from_cache = cached_payload is not None
    trace = start_evaluation_trace(
        langfuse_client,
        user_id=essay.user_id,
        essay_id=essay.id,
        task_type=payload.examType,
        from_cache=from_cache,
    )
    try:
        summary = await _run_evaluation(
            essay,
            cached_payload=cached_payload,
            coordinator=coordinator,
            trace=trace,
        )
    except EvaluationFailed as exc:
        essay.status = "evaluation_failed"
        db.commit()
        cache_hit_tracker.record(hit=False)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    persist_evaluation(db, essay, summary)
    _record_request(essay, summary, started=started, from_cache=from_cache)
    return _response(essay, summary, from_cache=from_cache)


@router.post("/{essay_id}/evaluate")
async def stream_essay_evaluation(
    essay_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    coordinator: EvaluationCoordinator = Depends(get_evaluation_coordinator),
    langfuse_client: Any = Depends(get_langfuse_client),
):
    essay = db.get(Essay, essay_id)
    if essay is None:
        raise HTTPException(status_code=404, detail="Essay not found")

    started = time.perf_counter()
    if not essay.evaluation_cache_key:
        essay.evaluation_cache_key = evaluation_cache_key(
            essay.extracted_text,
            essay.submission_type or "typed_text",
            essay.exam_type or essay.submission_type or "IELTS Writing",
            settings,
        )
    cached_payload = essay.evaluation_result or find_cached_evaluation(
        db, essay.evaluation_cache_key
    )
    from_cache = cached_payload is not None
    trace = start_evaluation_trace(
        langfuse_client,
        user_id=essay.user_id,
        essay_id=essay.id,
        task_type=essay.exam_type or essay.submission_type or "IELTS Writing",
        from_cache=from_cache,
    )

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_partial(result):
            await queue.put(("criterion", result.model_dump()))

        async def evaluate_in_background():
            try:
                summary = await _run_evaluation(
                    essay,
                    cached_payload=cached_payload,
                    coordinator=coordinator,
                    trace=trace,
                    on_partial=on_partial,
                )
                persist_evaluation(db, essay, summary)
                _record_request(
                    essay, summary, started=started, from_cache=from_cache
                )
                await queue.put(
                    (
                        "complete",
                        _response(
                            essay, summary, from_cache=from_cache
                        ).model_dump(),
                    )
                )
            except Exception as exc:
                essay.status = "evaluation_failed"
                db.commit()
                cache_hit_tracker.record(hit=False)
                await queue.put(("error", {"detail": str(exc)}))
            finally:
                await queue.put(None)

        task = asyncio.create_task(evaluate_in_background())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                event_name, data = event
                yield (
                    f"event: {event_name}\n"
                    f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
                )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@router.post("/evaluate/exam", response_model=ExamTaskEvaluationResponse)
async def evaluate_exam_task(
    payload: ExamTaskEvaluationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    coordinator: EvaluationCoordinator = Depends(get_evaluation_coordinator),
    langfuse_client: Any = Depends(get_langfuse_client),
):
    started = time.perf_counter()
    cache_key = evaluation_cache_key(
        payload.essayText,
        "exam",
        payload.examType,
        settings,
    )
    cached_payload = find_cached_evaluation(db, cache_key)
    essay = Essay(
        user_id=payload.userId,
        extracted_text=payload.essayText,
        submission_type="exam",
        exam_type=payload.examType,
        exam_session_id=payload.examSessionId,
        task_number=payload.taskNumber,
        evaluation_cache_key=cache_key,
        status="evaluating",
    )
    db.add(essay)
    db.commit()
    db.refresh(essay)
    from_cache = cached_payload is not None
    trace = start_evaluation_trace(
        langfuse_client,
        user_id=essay.user_id,
        essay_id=essay.id,
        task_type=payload.examType,
        from_cache=from_cache,
    )
    try:
        summary = await _run_evaluation(
            essay,
            cached_payload=cached_payload,
            coordinator=coordinator,
            trace=trace,
        )
    except EvaluationFailed as exc:
        essay.status = "evaluation_failed"
        db.commit()
        cache_hit_tracker.record(hit=False)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    persist_evaluation(db, essay, summary)
    _record_request(essay, summary, started=started, from_cache=from_cache)
    return _exam_response(
        essay,
        summary,
        exam_session_id=payload.examSessionId,
        task_number=payload.taskNumber,
        from_cache=from_cache,
    )
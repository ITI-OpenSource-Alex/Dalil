from __future__ import annotations

import asyncio

import structlog

from app.core.metrics import goa_exam_sessions_total
from app.repositories.heartbeat_repository import HeartbeatRepositoryProtocol

logger = structlog.get_logger("exam_service.sweep")


async def sweep_abandoned_sessions(
    repo: HeartbeatRepositoryProtocol,
) -> tuple[int, int]:
    checked, abandoned = await repo.sweep_abandoned()
    for session in abandoned:
        goa_exam_sessions_total.labels(
            skill_area=session["skill_area"],
            exam_type=session["exam_type"],
            outcome="abandoned",
        ).inc()
    logger.info(
        "sweep_completed",
        sessions_checked=checked,
        sessions_abandoned=len(abandoned),
    )
    return checked, len(abandoned)


async def run_sweep_loop(pool) -> None:
    from app.repositories.heartbeat_repository import HeartbeatRepository

    repo = HeartbeatRepository(pool)
    while True:
        await asyncio.sleep(300)
        try:
            await sweep_abandoned_sessions(repo)
        except Exception:
            logger.exception("sweep_error")

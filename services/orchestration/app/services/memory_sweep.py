"""The idle-session sweep that turns finished conversations into facts (GOA-038).

There is no "session ended" event anywhere in this system and no queue is being
introduced for one. A session is over when nobody has spoken in it for a while,
which is a question the sweep asks every few minutes.

Shaped after services/exam/app/services/sweep_service.py: a plain asyncio task
started in lifespan, one try/except per tick so a bad night cannot kill the
loop, and one structured log line per tick that is the thing you actually read
when checking whether it works.

Cost is a first-class concern here in a way it was not for the exam sweep. Every
candidate is a frontier-model call that is now genuinely billed, run unattended,
against sessions nobody is waiting on. Hence: a minimum turn count, a per-tick
batch cap, and a lock so a second replica cannot pay twice for the same session.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import structlog
from redis.asyncio import Redis as AsyncRedis

from app.core.config import settings
from app.core.metrics import (
    goa_orchestration_facts_conflicts_total,
    goa_orchestration_facts_extracted_total,
    goa_orchestration_facts_extraction_failures_total,
    goa_orchestration_facts_sweep_candidates,
)
from app.repositories.facts_repository import FactsRepository
from app.services import session_index as si
from app.services.fact_extraction import extract_facts
from app.services.facts_context import invalidate_facts_cache

logger = structlog.get_logger("orchestration.memory_sweep")

LOCK_PREFIX = "orch:facts:lock:"
LOCK_TTL_SECONDS = 600


@dataclass
class SweepResult:
    """What one tick did. Returned so tests assert on behaviour, not on log text."""

    candidates: int = 0
    locked_out: int = 0
    skipped_short: int = 0
    skipped_missing: int = 0
    extracted: int = 0
    facts_written: int = 0
    errors: int = 0
    purged: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)


async def _acquire_lock(redis: AsyncRedis, session_id: str) -> bool:
    """SET NX, so two replicas cannot both pay to extract the same session.

    Compose runs one replica today, so this is about the design surviving a
    second one rather than a bug reproducible now. The TTL means a worker that
    dies mid-extraction releases the session rather than stranding it forever.
    """
    return bool(
        await redis.set(f"{LOCK_PREFIX}{session_id}", "1", nx=True, ex=LOCK_TTL_SECONDS)
    )


async def _release_lock(redis: AsyncRedis, session_id: str) -> None:
    await redis.delete(f"{LOCK_PREFIX}{session_id}")


async def sweep_once(pool, redis: AsyncRedis, langfuse=None) -> SweepResult:
    """One pass: find quiet sessions, learn from them, forget the expired.

    Deliberately separate from the loop so it can be called directly by a test
    with a real database and a real Redis, with no sleeping involved.
    """
    result = SweepResult()
    repo = FactsRepository(pool)

    cutoff = time.time() - (settings.memory_idle_minutes * 60)
    candidates = await si.idle_sessions(redis, cutoff, settings.memory_sweep_batch_max)
    result.candidates = len(candidates)
    goa_orchestration_facts_sweep_candidates.set(len(candidates))

    for session_id in candidates:
        if not await _acquire_lock(redis, session_id):
            result.locked_out += 1
            continue

        try:
            meta = await si.session_meta(redis, session_id)
            if meta is None:
                # The 24-hour TTL expired out from under the index entry. There
                # is no transcript left to learn from either.
                result.skipped_missing += 1
                await si.drop_from_active(redis, session_id)
                continue

            if meta["turns"] < settings.memory_min_turns:
                # An abandoned "hi" is not worth a frontier-model call. Dropped
                # from the active set rather than reconsidered every five
                # minutes for the next day.
                result.skipped_short += 1
                await si.drop_from_active(redis, session_id)
                continue

            user_turns = await si.read_user_turns(redis, session_id)
            if not user_turns:
                result.skipped_missing += 1
                await si.drop_from_active(redis, session_id)
                continue

            trace = None
            trace_id = None
            if langfuse is not None:
                try:
                    # Its own root observation: the sweep runs outside any
                    # request, so there is no parent trace to hang it on.
                    trace = langfuse.start_observation(
                        name="fact_extraction",
                        as_type="span",
                        input={"session_id": session_id, "turns": len(user_turns)},
                        metadata={"user_id": meta["user_id"]},
                    )
                    trace_id = trace.trace_id
                except Exception as e:
                    logger.warning("Failed to start Langfuse observation", error=str(e))

            candidates_found = await extract_facts(
                user_turns,
                session_id=session_id,
                user_id=meta["user_id"],
                trace_id=trace_id,
            )

            written = 0
            for candidate in candidates_found:
                outcome = await repo.upsert_fact(meta["user_id"], candidate)
                goa_orchestration_facts_conflicts_total.labels(resolution=outcome).inc()
                result.outcomes[outcome] = result.outcomes.get(outcome, 0) + 1
                if outcome != "discarded":
                    goa_orchestration_facts_extracted_total.labels(
                        fact_type=candidate.fact_type
                    ).inc()
                    written += 1

            result.extracted += 1
            result.facts_written += written

            if written:
                # The request path caches facts for five minutes; a sweep that
                # wrote and did not invalidate would leave the next session
                # reading the state of the world from before this conversation.
                await invalidate_facts_cache(redis, meta["user_id"])

            # Only now, after everything succeeded. An exception above leaves
            # the session in the active set to be retried next tick.
            await si.drop_from_active(redis, session_id)

            if trace is not None:
                try:
                    trace.update(output={"facts_written": written})
                    trace.end()
                except Exception as e:
                    logger.warning("Failed to end Langfuse observation", error=str(e))

        except Exception as e:
            # One session's failure must not abort the batch.
            result.errors += 1
            goa_orchestration_facts_extraction_failures_total.inc()
            logger.warning(
                "Fact extraction failed for session",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
        finally:
            await _release_lock(redis, session_id)

    try:
        result.purged = await repo.purge_expired(settings.memory_fact_ttl_days)
    except Exception as e:
        logger.warning("Failed to purge expired facts", error=str(e))

    if langfuse is not None and result.extracted:
        try:
            # Flush per tick. Langfuse is otherwise flushed only at shutdown,
            # and a long-lived container would buffer a background job's traces
            # indefinitely -- which is how this service once logged "Langfuse
            # client initialized." and sent nothing for months.
            langfuse.flush()
        except Exception as e:
            logger.warning("Failed to flush Langfuse traces", error=str(e))

    logger.info(
        "memory_sweep_completed",
        candidates=result.candidates,
        extracted=result.extracted,
        facts_written=result.facts_written,
        skipped_short=result.skipped_short,
        skipped_missing=result.skipped_missing,
        locked_out=result.locked_out,
        errors=result.errors,
        purged=result.purged,
    )
    return result


async def run_sweep_loop(pool, langfuse=None) -> None:
    """The background task. Sleeps first, so startup is never blocked by a sweep."""
    redis = await si.get_redis_client()
    try:
        while True:
            await asyncio.sleep(settings.memory_sweep_interval_seconds)
            try:
                await sweep_once(pool, redis, langfuse=langfuse)
            except Exception:
                logger.exception("memory_sweep_error")
    finally:
        await redis.aclose()

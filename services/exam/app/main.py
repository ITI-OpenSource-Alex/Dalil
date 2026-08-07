import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
import structlog

from app.api.heartbeat import router as heartbeat_router
from app.api.history import router as history_router
from app.api.internal import router as internal_router
from app.api.listening import router as listening_router
from app.api.questions import router as questions_router
from app.api.reading import router as reading_router
from app.api.results import router as results_router
from app.api.sessions import router as sessions_router
from app.core.database import db
from app.core.exam_observability import refresh_question_bank_size
from app.core.logging import configure_logging, correlation_id_var
from app.repositories.question_repository import QuestionRepository
from app.services.sweep_service import run_sweep_loop
from app.services.account_deletion_consumer import consume_account_deleted_messages

configure_logging()
logger = structlog.get_logger("exam_service.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Exam service...")
    await db.connect()
    logger.info("Exam service database connected and migrations checked.")

    # Seed the question-bank-size gauge so the "drops unexpectedly" alarm has a
    # baseline before the first /question-bank/stats call. Non-fatal: a failure
    # here must not block startup.
    try:
        stats = await QuestionRepository(db.pool).get_question_bank_stats()
        refresh_question_bank_size(stats)
    except Exception:
        logger.exception("Failed to seed question bank size gauge on startup")

    sweep_task = asyncio.create_task(run_sweep_loop(db.pool))
    account_deleted_task = asyncio.create_task(consume_account_deleted_messages())
    yield

    sweep_task.cancel()
    account_deleted_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    try:
        await account_deleted_task
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down Exam service...")
    await db.disconnect()
    logger.info("Exam service database connection closed.")


app = FastAPI(
    title="GOA Exam Service",
    description="Python-based Exam Service scaffold for GOA",
    version="1.0.0",
    lifespan=lifespan,
)

# Local development calls this service directly from the browser on
# localhost:8085, bypassing the gateway (see docs/local-dev-setup.md's
# "Gateway vs. Direct Calls" section) - the same pattern already handled for
# the Speaking service in services/speaking/internal/speaking/cors.go.
# Without this, the browser's CORS preflight (OPTIONS) for any request
# carrying the x-internal-api-key header or a JSON body gets a 405 with no
# Access-Control-* headers, and the browser blocks the real request before
# it's ever sent - the server itself never sees anything wrong.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-Internal-API-Key"],
)


# Inject Correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id")
    token = None
    if correlation_id:
        token = correlation_id_var.set(correlation_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        # Emit one structured line per request.
        #
        # Correlation propagation was already correct end to end -- the gateway
        # generates an ID, forwards it, and it reaches this middleware -- but no
        # handler on any gateway-reachable path logged anything, so requests
        # appeared only in uvicorn's access log, which has no correlation field.
        # The ID was carried faithfully to a place where it was never written
        # down, which makes tracing a request across services impossible in
        # practice and GW-03 unverifiable as written (BUG-030).
        #
        # inject_correlation_id picks correlation_id up from the context var set
        # above, so it lands on this line and on anything a handler logs within
        # the request.
        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return response
    except Exception:
        logger.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        raise
    finally:
        if token is not None:
            correlation_id_var.reset(token)


# Mount routers directly
app.include_router(sessions_router)
app.include_router(heartbeat_router)
app.include_router(questions_router)
app.include_router(results_router)
app.include_router(reading_router)
app.include_router(listening_router)
app.include_router(internal_router)
app.include_router(history_router)


# Health endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Metrics endpoint using standard prometheus client exporter
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)



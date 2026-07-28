import asyncio
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
from app.core.logging import configure_logging, correlation_id_var
from app.services.sweep_service import run_sweep_loop

configure_logging()
logger = structlog.get_logger("exam_service.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Exam service...")
    await db.connect()
    logger.info("Exam service database connected and migrations checked.")

    sweep_task = asyncio.create_task(run_sweep_loop(db.pool))
    yield

    sweep_task.cancel()
    try:
        await sweep_task
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
    try:
        response = await call_next(request)
        return response
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

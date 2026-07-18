from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
import structlog
from app.core.database import db
from app.core.logging import configure_logging, correlation_id_var
from app.api.query import router as query_router
from app.api.visa import router as visa_router
from app.api.documents import router as documents_router
from app.core.redis import redis_client
from app.api.scoring import router as scoring_router
from app.api.scoring import match_router as match_router

from contextlib import asynccontextmanager
import asyncio
from app.services.sqs_consumer import consume_sqs_messages
from app.api.program_requirements import router as program_requirements_router
from app.api.scholarship_programs import router as scholarship_programs_router

configure_logging()
logger = structlog.get_logger("rag_service.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Starting up RAG service...")
    await db.connect()
    await redis_client.connect()
    logger.info("RAG service database connected and migrations checked.")

    # Start the background SQS consumer task
    sqs_task = asyncio.create_task(consume_sqs_messages())

    yield  # App is running and serving requests here

    # --- Shutdown ---
    logger.info("Shutting down RAG service...")
    sqs_task.cancel()  # Tell the background task to stop
    try:
        await sqs_task
    except asyncio.CancelledError:
        pass

    await db.disconnect()
    await redis_client.disconnect()
    logger.info("RAG service database connection closed.")


app = FastAPI(
    title="GOA RAG Service",
    description="Python-based RAG Service scaffold for GOA",
    version="1.0.0",
    lifespan=lifespan,
)


# Inject Correlation ID middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-Id")
    if correlation_id:
        correlation_id_var.set(correlation_id)
    response = await call_next(request)
    return response


# Mount routers directly
app.include_router(query_router)
app.include_router(visa_router)
app.include_router(documents_router)
app.include_router(program_requirements_router)
app.include_router(scholarship_programs_router)
# Health endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Metrics endpoint using standard prometheus client exporter
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
app.include_router(scoring_router)
app.include_router(match_router)

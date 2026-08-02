import asyncio
import httpx
import structlog
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app
from langfuse import Langfuse


from app.core.config import settings
from app.core.database import db
from app.services.memory_sweep import run_sweep_loop
from app.api.chat import router as chat_router
from app.api.memory import router as memory_router


# Configure structlog for JSON logs
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger("orchestration.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Orchestration service...")
    #Instantiate shared httpx.AsyncClient for connection pooling
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("Shared HTTPX AsyncClient instantiated.")

    # Postgres, for GOA-038's long-term facts. Migrations run inside connect().
    #
    # A failure here is deliberately NOT fatal. Chat has worked without a
    # database for three sprints and must keep working without one: memory is
    # enrichment, and taking the whole conversational surface offline because a
    # fact table is unreachable would be a far worse outage than forgetting who
    # the user is. /health reports the degradation instead.
    try:
        await db.connect()
        logger.info(
            "Orchestration database connected and migrations checked.",
            migrations_applied=db.migrations_applied,
        )
    except Exception as e:
        logger.error(
            "Database unavailable at startup - long-term memory disabled for this process",
            error=str(e),
        )

    if settings.langfuse_public_key and settings.langfuse_secret_key:
        app.state.langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host
        )
        logger.info("Langfuse client initialized.")
    else:
        logger.warning("Langfuse keys not set. Tracing will be inactive.")
        app.state.langfuse = None

    # The idle-session sweep (GOA-038). No "session ended" event exists in this
    # system and none is being introduced, so a session is considered over when
    # nobody has spoken in it for MEMORY_IDLE_MINUTES.
    sweep_task = None
    if settings.memory_enabled and db.pool is not None:
        sweep_task = asyncio.create_task(run_sweep_loop(db.pool, app.state.langfuse))
        logger.info(
            "Long-term memory sweep started",
            interval_seconds=settings.memory_sweep_interval_seconds,
            idle_minutes=settings.memory_idle_minutes,
        )
    else:
        logger.warning(
            "Long-term memory sweep not started",
            memory_enabled=settings.memory_enabled,
            database_available=db.pool is not None,
        )

    yield

    if sweep_task is not None:
        sweep_task.cancel()
        try:
            await sweep_task
        except asyncio.CancelledError:
            pass

     # Teardown
    logger.info("Shutting down Orchestration service...")
    
    # 3. Close the shared HTTPX Client
    await app.state.http_client.aclose()
    logger.info("Shared HTTPX AsyncClient closed.")
    
    # 4. Flush Langfuse buffer to prevent trace loss on exit
    if app.state.langfuse:
        app.state.langfuse.flush()
        logger.info("Langfuse traces flushed.")

    # 5. Close the Postgres pool
    await db.disconnect()
    logger.info("Orchestration database connection closed.")

app = FastAPI(
    title="GOA Orchestration Service",
    description="FastAPI + LangChain Supervisor Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(chat_router)
app.include_router(memory_router)



# Correlation ID Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Retrieve correlation ID from headers or generate a new one
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response
# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
# Health endpoint
#
# This used to return {"status": "healthy"} unconditionally, which was honest
# while the service had no dependencies it could lose. Now that facts live in
# Postgres, an unconditional 200 would let a container whose migrations failed
# sit in a load balancer reporting healthy while every write 500s -- and the
# database being down is exactly the condition a health check exists to surface.
#
# "degraded" rather than "unhealthy": chat still works without the database, so
# this is a 503 that means "do not send me traffic if you have a better option",
# not "I am dead".
@app.get("/health")
async def health_check():
    db_ok = await db.healthy()
    body = {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "migrations": db.migrations_applied,
    }
    if db_ok:
        return body
    return JSONResponse(status_code=503, content=body)
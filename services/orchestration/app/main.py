import httpx
import structlog
import uuid
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app
from langfuse import Langfuse


from app.core.config import settings
from app.api.chat import router as chat_router


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
    yield

     # Teardown
    logger.info("Shutting down Orchestration service...")
    
    # 3. Close the shared HTTPX Client
    await app.state.http_client.aclose()
    logger.info("Shared HTTPX AsyncClient closed.")
    
    # 4. Flush Langfuse buffer to prevent trace loss on exit
    if app.state.langfuse:
        app.state.langfuse.flush()
        logger.info("Langfuse traces flushed.")

app = FastAPI(
    title="GOA Orchestration Service",
    description="FastAPI + LangChain Supervisor Agent",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(chat_router)



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
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
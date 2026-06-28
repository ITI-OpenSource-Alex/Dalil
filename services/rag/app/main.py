from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
import structlog
from app.core.database import db
from app.core.logging import configure_logging, correlation_id_var
from app.api.query import router as query_router
from app.api.visa import router as visa_router
from app.api.documents import router as documents_router

configure_logging()
logger = structlog.get_logger("rag_service.main")

app = FastAPI(
    title="GOA RAG Service",
    description="Python-based RAG Service scaffold for GOA",
    version="1.0.0"
)

# Startup & Shutdown lifecycle handlers
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up RAG service...")
    await db.connect()
    logger.info("RAG service database connected and migrations checked.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down RAG service...")
    await db.disconnect()
    logger.info("RAG service database connection closed.")

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
# Health endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Metrics endpoint using standard prometheus client exporter
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
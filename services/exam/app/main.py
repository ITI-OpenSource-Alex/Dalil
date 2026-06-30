from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
import structlog
from app.api.questions import router as questions_router
from app.api.results import router as results_router
from app.api.sessions import router as sessions_router
from app.core.database import db
from app.core.logging import configure_logging, correlation_id_var

configure_logging()
logger = structlog.get_logger("exam_service.main")

app = FastAPI(
    title="GOA Exam Service",
    description="Python-based Exam Service scaffold for GOA",
    version="1.0.0"
)

# Startup & Shutdown lifecycle handlers
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Exam service...")
    await db.connect()
    logger.info("Exam service database connected and migrations checked.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Exam service...")
    await db.disconnect()
    logger.info("Exam service database connection closed.")

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
app.include_router(questions_router)
app.include_router(results_router)

# Health endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Metrics endpoint using standard prometheus client exporter
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

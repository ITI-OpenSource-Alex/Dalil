import time
import httpx
import structlog
from typing import AsyncGenerator
from app.core.config import settings
from app.core.metrics import goa_orchestration_downstream_latency_ms

logger = structlog.get_logger("orchestration.client")


async def forward_downstream_stream(
        client: httpx.AsyncClient,
        intent: str,
        message: str,
        user_id: str,
        correlation_id: str
) -> AsyncGenerator[str, None]:
    """
    Calls the appropriate downstream service based on intent, propagates tracking headers,
    measures latency, and yields response tokens chunk-by-chunk.
    Implements a graceful fallback (circuit breaker) if the downstream service is offline.
    """


    headers = {
        "X-Internal-Api-Key": settings.internal_api_key,
        "X-Correlation-Id": correlation_id,
        "Content-Type": "application/json"
    }

     # 1. Determine target service and URL based on intent classification
    service_name = intent.lower()
    target_url = ""
    payload = {}
    if intent == "RAG" or intent == "OPPORTUNITY_SEARCH":
        # OPPORTUNITY_SEARCH implicitly routes to RAG in Sprint 1
        target_url = f"{settings.rag_service_url}/query"
        payload = {"question": message, "userId": user_id}
        service_name = "rag"
    elif intent == "WRITING" or intent == "CV_REVIEW":
        # CV_REVIEW implicitly routes to Writing in Sprint 1
        target_url = f"{settings.writing_service_url}/essays"
        payload = {
            "userId": user_id,
            "essayText": message,
            "submissionType": "task2"
        }
        service_name = "writing"
    elif intent == "SPEAKING":
        target_url = f"{settings.speaking_service_url}/chat"
        payload = {"message": message, "userId": user_id}
        service_name = "speaking"
    logger.info(
        "Routing message downstream",
        intent=intent,
        service=service_name,
        url=target_url,
        correlation_id=correlation_id
    )
    start_time = time.perf_counter()

    try:
        # In Sprint 1, RAG and Writing are non-streaming REST endpoints.
        # We call them and yield their responses chunk-by-chunk to simulate streaming.
        # Speaking has no REST endpoint, so it will raise an exception or 404,
        # triggering the fallback block.

        response = await client.post(target_url, json=payload, headers=headers, timeout=10.0)
        #Observe downstream latency
        duration_ms = (time.perf_counter() - start_time) * 1000
        goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
        if response.status_code == 200:
            data = response.json()
            if service_name == "rag":
                answer = data.get("answer", "No answer received.")
            elif service_name == "writing":
                essay_id = data.get("id", "unknown")
                status = data.get("status", "ready")
                answer = f"Essay submitted successfully! ID: {essay_id}. Status: {status}."
            else:
                answer = str(data)
            # Yield chunks to simulate streaming
            chunk_size = 5
            for i in range(0, len(answer), chunk_size):
                yield answer[i:i + chunk_size]
        else:
            logger.error(
                "Downstream service returned error status",
                status_code=response.status_code,
                text=response.text
            )
            response.raise_for_status()
    except (httpx.HTTPError, Exception) as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "Downstream service unavailable - activating fallback",
            service=service_name,
            error=str(e),
            latency_ms=duration_ms
        )
        
        # Observe latency even for failures
        goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
        # Graceful fallback messages (Circuit Breaker pattern)
        if intent == "SPEAKING":
            yield "I'm sorry, but the Speaking practice service is currently offline. Please try again later."
        elif intent == "WRITING" or intent == "CV_REVIEW":
            yield "I'm sorry, but the Writing evaluation service is currently offline. Please try again later."
        elif intent == "RAG" or intent == "OPPORTUNITY_SEARCH":
            yield "I'm sorry, but the global opportunity database is currently offline. Please try again later."
        else:
            yield "I'm sorry, but the requested service is currently unavailable."
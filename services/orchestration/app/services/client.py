import time
import datetime
import httpx
import structlog
import pybreaker
import contextvars
from typing import AsyncGenerator, List, Optional

correlation_id_var = contextvars.ContextVar("correlation_id", default="unknown")
from app.core.config import settings
from app.core.metrics import goa_orchestration_downstream_latency_ms, goa_orchestration_circuit_breaker_state
from app.schemas.chat import ChatStreamEvent

logger = structlog.get_logger("orchestration.client")


class MetricsCircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """
    Listens to Pybreaker state changes to update Prometheus metrics
    and log structured JSON errors for correlation.
    """
    def __init__(self, service_name: str):
        self.service_name = service_name

    def state_change(self, cb, old_state, new_state):
        if new_state.name == "open":
            goa_orchestration_circuit_breaker_state.labels(service=self.service_name).set(1)
            logger.error(
                "Circuit breaker opened",
                service=self.service_name,
                failure_count=cb.fail_counter,
                opened_at=time.time(),
                correlation_id=correlation_id_var.get()
            )
        elif new_state.name == "closed":
            goa_orchestration_circuit_breaker_state.labels(service=self.service_name).set(0)
            
            downtime_s = 0.0
            if cb._state_storage.opened_at:
                downtime_s = (datetime.datetime.now(pybreaker.UTC) - cb._state_storage.opened_at).total_seconds()
                
            logger.info(
                "Circuit breaker closed",
                service=self.service_name,
                closed_at=time.time(),
                downtime_s=downtime_s
            )


rag_breaker = pybreaker.CircuitBreaker(
    fail_max=3, 
    reset_timeout=60, 
    listeners=[MetricsCircuitBreakerListener("rag")]
)
writing_breaker = pybreaker.CircuitBreaker(
    fail_max=3, 
    reset_timeout=60, 
    listeners=[MetricsCircuitBreakerListener("writing")]
)

async def call_with_breaker(breaker: pybreaker.CircuitBreaker, client: httpx.AsyncClient, url: str, payload: dict, headers: dict):
    state = breaker.current_state
    if state == "open":
        opened_at = breaker._state_storage.opened_at
        if opened_at:
            timeout = datetime.timedelta(seconds=breaker.reset_timeout)
            if opened_at + timeout < datetime.datetime.now(pybreaker.UTC):
                breaker.half_open()
            else:
                raise pybreaker.CircuitBreakerError("Circuit is open")
        else:
            raise pybreaker.CircuitBreakerError("Circuit is open")

    try:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code < 500:
            raise e
        if breaker.is_system_error(e):
            def fail(): raise e
            try: breaker.call(fail)
            except Exception: pass
        raise e
    except Exception as e:
        if breaker.is_system_error(e):
            def fail(): raise e
            try: breaker.call(fail)
            except Exception: pass
        raise e
        
    breaker.call(lambda: None)
    return data
        



async def call_rag(client: httpx.AsyncClient, url: str, payload: dict, headers: dict):
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

async def call_writing(client: httpx.AsyncClient, url: str, payload: dict, headers: dict):
    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


async def forward_downstream_stream(
        client: httpx.AsyncClient,
        intent: str,
        message: str,
        user_id: str,
        correlation_id: str,
        attachments: Optional[List[str]] = None
) -> AsyncGenerator[ChatStreamEvent, None]:
    """
    Routes the request to the target microservice based on intent classification.
    Yields strictly-typed ChatStreamEvent objects to ensure frontend contract integrity.
    """
    headers = {
        "X-Internal-Api-Key": settings.internal_api_key,
        "X-Correlation-Id": correlation_id,
        "Content-Type": "application/json"
    }

    intent = intent.upper()
    correlation_id_var.set(correlation_id)
    
    if intent == "SPEAKING":
        ws_url = f"{settings.speaking_service_url.replace('http', 'ws')}/ws"
        yield ChatStreamEvent(type="speaking_url", wsUrl=ws_url)
        return

    service_name = ""
    start_time = time.perf_counter()

    try:
        if intent == "WRITING":
            service_name = "writing"
            url = f"{settings.writing_service_url}/essays"
            payload = {"userId": user_id, "essayText": message, "submissionType": "task2"}
            
            logger.info("Routing message downstream", intent=intent, service=service_name, url=url, correlation_id=correlation_id)
            data = await call_with_breaker(writing_breaker,client, url, payload, headers)
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
            
            essay_id = data.get("id", "unknown")
            sse_url = f"{settings.writing_service_url}/essays/{essay_id}/evaluate"
            yield ChatStreamEvent(type="writing_url", essayId=essay_id, sseUrl=sse_url)

        elif intent == "RAG":
            service_name = "rag"
            url = f"{settings.rag_service_url}/query"
            payload = {"question": message, "userId": user_id}
            
            logger.info("Routing message downstream", intent=intent, service=service_name, url=url, correlation_id=correlation_id)
            data = await call_with_breaker(rag_breaker, client, url, payload, headers)
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
            
            answer = data.get("answer", "No answer received.")
            import asyncio
            chunk_size = 5
            for i in range(0, len(answer), chunk_size):
                await asyncio.sleep(0.02)
                yield ChatStreamEvent(type="token", content=answer[i:i + chunk_size])
            
            sources = data.get("sources", [])
            if sources:
                yield ChatStreamEvent(type="sources", sources=sources)

        elif intent == "OPPORTUNITY_SEARCH":
            service_name = "rag"
            url = f"{settings.rag_service_url}/match"
            payload = {"userId": user_id}
            
            logger.info("Routing message downstream", intent=intent, service=service_name, url=url, correlation_id=correlation_id)
            data = await call_with_breaker(rag_breaker, client, url, payload, headers)
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
            
            programs = data.get("programs", [])
            yield ChatStreamEvent(type="match_results", programs=programs)

        elif intent == "CV_REVIEW":
            service_name = "writing"
            url = f"{settings.writing_service_url}/essays"
            cv_text = attachments[0] if attachments else message
            payload = {"userId": user_id, "essayText": cv_text, "submissionType": "task2"}
            
            logger.info("Routing CV downstream to Writing", intent=intent, service=service_name, url=url, correlation_id=correlation_id)
            data = await call_with_breaker(writing_breaker ,client, url, payload, headers)
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)

            # CV Workflow Part 2: Extract text and feed to RAG
            service_name = "rag"
            rag_url = f"{settings.rag_service_url}/query"
            rag_payload = {"question": f"Review this CV: {cv_text}", "userId": user_id}
            start_time_rag = time.perf_counter()
            
            logger.info("Routing extracted CV downstream to RAG", intent=intent, service=service_name, url=rag_url, correlation_id=correlation_id)
            data = await call_with_breaker(rag_breaker,client, rag_url, rag_payload, headers)
            duration_ms_rag = (time.perf_counter() - start_time_rag) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms_rag)

            answer = data.get("answer", "No answer received.")
            chunk_size = 5
            import asyncio
            for i in range(0, len(answer), chunk_size):
                await asyncio.sleep(0.02)
                yield ChatStreamEvent(type="token", content=answer[i:i + chunk_size])
            
            sources = data.get("sources", [])
            if sources:
                yield ChatStreamEvent(type="sources", sources=sources)

    except pybreaker.CircuitBreakerError:
        if intent in ["WRITING", "CV_REVIEW"]:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the Writing evaluation service is currently offline. Please try again later.")
        else:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the global opportunity database is currently offline. Please try again later.")
    except (httpx.HTTPError, Exception) as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "Downstream service unavailable - activating fallback",
            service=service_name,
            error=str(e),
            latency_ms=duration_ms,
            correlation_id=correlation_id
        )
        goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
        
        # We explicitly log ReadTimeouts differently for clarity
        if isinstance(e, httpx.ReadTimeout):
            logger.error(f"Timeout (30s) reached connecting to {service_name}")
            
        if intent in ["WRITING", "CV_REVIEW"]:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the Writing evaluation service is currently offline. Please try again later.")
        else:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the global opportunity database is currently offline. Please try again later.")
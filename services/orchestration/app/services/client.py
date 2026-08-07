import time
import datetime
import asyncio
import httpx
import structlog
import pybreaker
import contextvars
from typing import AsyncGenerator, Dict, List, Optional
from urllib.parse import quote

correlation_id_var = contextvars.ContextVar("correlation_id", default="unknown")
from app.core.config import settings
from app.core.metrics import goa_orchestration_downstream_latency_ms, goa_orchestration_circuit_breaker_state
from app.schemas.chat import ChatStreamEvent
from app.services.output_filter import filter_response
from app.services.supervisor import SUPERVISOR_CANARIES

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


def _build_exam_prep_response(message: str, exam_context: Optional[Dict] = None) -> str:
    """
    Build a personalised EXAM_PREP response grounded in the user's exam data.

    Ticket GOA-060 mandates: no generic advice.  Every response MUST
    reference the user's specific weak criterion, suggest a Cambridge test,
    and provide a link to ``/exam``.
    """
    if not exam_context or exam_context.get("exam_count", 0) == 0:
        return (
            "I don't have any exam history for you yet. "
            "Take a practice exam at /exam so I can give you targeted advice "
            "based on your actual performance."
        )

    latest_bands = exam_context.get("latest_bands") or {}
    weak_areas = exam_context.get("weak_areas") or {}

    # Identify the weakest skill by lowest band score
    weakest_skill = None
    weakest_band = None
    for skill in ("reading", "listening", "writing", "speaking"):
        band = latest_bands.get(skill)
        if band is not None and (weakest_band is None or band < weakest_band):
            weakest_band = band
            weakest_skill = skill

    parts: list[str] = []

    # Reference specific weak criterion
    if weak_areas:
        for skill, criterion in weak_areas.items():
            band = latest_bands.get(skill, "N/A")
            parts.append(
                f"Your latest {skill.title()} band is {band}, "
                f"and the specific area to improve is **{criterion}**."
            )
    elif weakest_skill:
        parts.append(
            f"Your weakest skill is {weakest_skill.title()} "
            f"at band {weakest_band}."
        )

    # Suggest a specific Cambridge test
    skill_for_test = list(weak_areas.keys())[0] if weak_areas else (weakest_skill or "reading")
    cambridge_suggestions = {
        "reading": "Cambridge IELTS 18, Test 2, Reading Passage 3",
        "listening": "Cambridge IELTS 17, Test 1, Section 4",
        "writing": "Cambridge IELTS 18, Test 3, Writing Task 2",
        "speaking": "Cambridge IELTS 17, Test 2, Speaking Part 2",
    }
    suggestion = cambridge_suggestions.get(skill_for_test, "Cambridge IELTS 18, Test 1")
    parts.append(f"I recommend practising with **{suggestion}** to target this weakness.")

    # Link to /exam
    parts.append("Start a focused practice session now at **/exam**.")

    return " ".join(parts)


async def forward_downstream_stream(
        client: httpx.AsyncClient,
        intent: str,
        message: str,
        user_id: str,
        correlation_id: str,
        attachments: Optional[List[str]] = None,
        exam_context: Optional[Dict] = None,
        traceparent: Optional[str] = None,
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
    if traceparent:
        headers["traceparent"] = traceparent

    intent = intent.upper()
    correlation_id_var.set(correlation_id)

    if intent == "SPEAKING":
        # A browser-reachable URL, not the Docker hostname. Deriving it from
        # speaking_service_url produced ws://speaking:8082/ws, which no browser can
        # resolve, so the SPEAKING intent was dead end to end (BUG-016).
        #
        # GOA-132: this now points at the Gateway's WebSocket proxy, so the
        # session is authenticated at upgrade time and carries a correlation ID
        # into Speaking's logs. The browser sends its access_token cookie on the
        # handshake, which is why no token is embedded in this URL.
        ws_url = settings.public_speaking_ws_url
        if traceparent:
            separator = "&" if "?" in ws_url else "?"
            ws_url = (
                f"{ws_url}{separator}traceparent="
                f"{quote(traceparent, safe='-')}"
            )
        yield ChatStreamEvent(type="speaking_url", wsUrl=ws_url)
        return

    if intent == "EXAM_PREP":
        answer = _build_exam_prep_response(message, exam_context)
        chunk_size = 5
        for i in range(0, len(answer), chunk_size):
            await asyncio.sleep(0.02)
            yield ChatStreamEvent(type="token", content=answer[i:i + chunk_size])
        yield ChatStreamEvent(type="exam_prep", content="/exam")
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
            
            # Writing's Essay.id is an integer primary key, but essayId crosses the
            # wire as a string (ChatStreamEvent, and GOA-019's client reads it as
            # one). Without this cast Pydantic rejects the event and the WRITING
            # intent fails outright -- see BUG-015: the service answered correctly
            # and the user was still told it was offline.
            essay_id = data.get("id", "unknown")
            # Route the client through the Gateway rather than at the Writing
            # service directly. writing_service_url is a Docker hostname the
            # browser cannot resolve (BUG-016), and going via the Gateway means
            # this stream carries JWT auth, rate limiting and a correlation ID
            # like every other client call.
            sse_url = (
                f"{settings.public_gateway_url}/api/writing/essays/{essay_id}/evaluate"
            )
            if traceparent:
                sse_url = (
                    f"{sse_url}?traceparent={quote(traceparent, safe='-')}"
                )
            yield ChatStreamEvent(type="writing_url", essayId=str(essay_id), sseUrl=sse_url)

        elif intent == "RAG":
            service_name = "rag"
            url = f"{settings.rag_service_url}/query"
            payload = {"question": message, "userId": user_id}
            
            logger.info("Routing message downstream", intent=intent, service=service_name, url=url, correlation_id=correlation_id)
            data = await call_with_breaker(rag_breaker, client, url, payload, headers)
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
            
            # GOA-033 gave RAG a refusal contract: when retrieval confidence is
            # too low it returns answer=null with a `reason` and a `suggestion`
            # written for the user. Orchestration never consumed it. `.get()`
            # returns None for a key that exists with a null value, so len(None)
            # raised TypeError into the generic handler below and the user was
            # told "the global opportunity database is currently offline" -- a
            # false statement about a healthy service that had just answered
            # correctly, and the same shape as BUG-015.
            #
            # Found by the GOA-034 pentest: every adversarial payload retrieves
            # nothing and so trips the threshold, which made it obvious that any
            # ordinary off-topic question does too.
            answer = data.get("answer")
            if not answer:
                answer = data.get("suggestion") or (
                    "I could not find enough information to answer that reliably. "
                    "Try asking about a specific university, programme or visa requirement."
                )
                logger.info(
                    "RAG declined to answer; relaying its suggestion",
                    reason=data.get("reason"),
                    correlation_id=correlation_id,
                )
            # GOA-034: the last moment this text exists whole. Once the loop
            # below starts emitting five-character chunks, the first of them
            # has already left and nothing downstream can be recalled.
            answer = filter_response(
                answer,
                user_id=user_id,
                correlation_id=correlation_id,
                intent=intent,
                leak_fragments=SUPERVISOR_CANARIES,
            )
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

            # Same refusal contract as the RAG branch above, and the same bug:
            # a CV whose review retrieves nothing confident produced "the
            # database is offline" instead of RAG's own suggestion.
            answer = data.get("answer")
            if not answer:
                answer = data.get("suggestion") or (
                    "I could not review that reliably. Try uploading a CV with "
                    "more detail about your education and experience."
                )
                logger.info(
                    "RAG declined to review; relaying its suggestion",
                    reason=data.get("reason"),
                    correlation_id=correlation_id,
                )
            # GOA-034: the last moment this text exists whole. Once the loop
            # below starts emitting five-character chunks, the first of them
            # has already left and nothing downstream can be recalled.
            answer = filter_response(
                answer,
                user_id=user_id,
                correlation_id=correlation_id,
                intent=intent,
                leak_fragments=SUPERVISOR_CANARIES,
            )
            chunk_size = 5
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
        # Distinguish "they didn't answer" from "we couldn't handle their answer".
        # This handler catches bare Exception, so a local bug -- a Pydantic
        # ValidationError on our own event schema, say -- used to be logged and
        # reported as a downstream outage. BUG-015 was exactly that: the Writing
        # service returned 201 with a valid essay and the log read "Downstream
        # service unavailable", pointing debugging at the wrong service entirely.
        is_downstream_fault = isinstance(e, httpx.HTTPError)
        logger.warning(
            "Downstream service unavailable - activating fallback"
            if is_downstream_fault
            else "Orchestration failed to process a successful downstream response",
            service=service_name,
            error=str(e),
            error_type=type(e).__name__,
            downstream_fault=is_downstream_fault,
            latency_ms=duration_ms,
            correlation_id=correlation_id
        )
        goa_orchestration_downstream_latency_ms.labels(service=service_name).observe(duration_ms)
        
        # We explicitly log ReadTimeouts differently for clarity
        if isinstance(e, httpx.ReadTimeout):
            logger.error(
                "Read timeout reached waiting for downstream service",
                service=service_name,
                read_timeout_s=settings.downstream_read_timeout_seconds,
            )
            
        if intent in ["WRITING", "CV_REVIEW"]:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the Writing evaluation service is currently offline. Please try again later.")
        else:
            yield ChatStreamEvent(type="error", error="I'm sorry, but the global opportunity database is currently offline. Please try again later.")

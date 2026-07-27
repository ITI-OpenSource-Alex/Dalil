import time
import json
import asyncio
import structlog
from typing import List
from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import ServerSentEvent, EventSourceResponse
from app.schemas.chat import ChatRequest, HistoryResponseItem, ChatStreamEvent
from app.services.supervisor import classify_intent
from app.services.memory import get_session_memory, load_memory_variables, save_context
from app.services.client import forward_downstream_stream
logger = structlog.get_logger("orchestration.api.chat")
router = APIRouter()



@router.post("/chat")
async def chat_endpoint(request: ChatRequest, req: Request):
    """
    Handles user chat requests. Classifies message intent, retrieves/updates session
    history in Redis, routes to the appropriate downstream service, and streams
    results back to the client using Server-Sent Events (SSE).
    """
    start_time = time.perf_counter()
    correlation_id = req.state.correlation_id
    # 1. Initialize Langfuse root trace
    trace = None
    supervisor_span = None
    langfuse_client = req.app.state.langfuse
    if langfuse_client:
        try:
            # Langfuse v3 removed client.trace()/trace.span() in favour of
            # observations. This code was still calling the v2 API against an
            # unpinned langfuse>=3.0.0 that resolved to 4.x, so every call raised
            # AttributeError into the except below, logged a warning and carried
            # on -- startup said "Langfuse client initialized." while not one
            # trace ever reached Langfuse (BUG-032).
            trace = langfuse_client.start_observation(
                name="chat_request",
                as_type="span",
                input={"message": request.message},
                metadata={
                    "correlation_id": correlation_id,
                    "user_id": request.userId,
                    "session_id": request.sessionId,
                },
            )
            supervisor_span = trace.start_observation(
                name="supervisor_routing",
                as_type="span",
                input={"message": request.message},
            )
        except Exception as e:
            logger.warning("Failed to initialize Langfuse trace/span", error=str(e))
    async def event_generator():
        nonlocal supervisor_span
        full_response = ""
        intent = "RAG"
        downstream_service = "rag"
        status = "success"
        try:
            # 2. Classify intent via structured LLM call
            # v4 splits what v2 called trace.id: .trace_id is the trace, .id is
            # this observation. classify_intent wants the trace plus the span to
            # parent its LLM generation under.
            trace_id = trace.trace_id if trace else None
            parent_span_id = supervisor_span.id if supervisor_span else None
            
            intent_result = await classify_intent(
                message=request.message,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                user_id=request.userId
            )
            intent = intent_result.intent
            downstream_service = intent.lower()
            if supervisor_span:
                try:
                    # v4's end() takes only end_time; the output goes via update().
                    supervisor_span.update(output=intent_result.model_dump())
                    supervisor_span.end()
                except Exception as e:
                    logger.warning("Failed to end Langfuse supervisor span", error=str(e))
            # 3. Stream intent classification metadata as the first SSE chunk
            yield ServerSentEvent(
                event="metadata",
                data=ChatStreamEvent(
                    type="metadata",
                    intent=intent,
                    confidence=intent_result.confidence
                ).model_dump_json()
            )
            # 4. Load memory variables using thread pool executor
            memory = get_session_memory(request.sessionId)
            await load_memory_variables(memory, {"input": request.message})
            # 5. Initialize downstream call trace span
            downstream_span = None
            if trace:
                try:
                    downstream_span = trace.start_observation(
                        name="downstream_call",
                        as_type="span",
                        input={"intent": intent, "message": request.message},
                    )
                except Exception as e:
                    logger.warning("Failed to initialize Langfuse downstream span", error=str(e))
            # 6. Stream content tokens from downstream service
            response_stream = forward_downstream_stream(
                client=req.app.state.http_client,
                intent=intent,
                message=request.message,
                user_id=request.userId,
                correlation_id=correlation_id,
                attachments=request.attachments
            )
            async for event in response_stream:
                if event.type == "token" and event.content:
                    full_response += event.content
                yield ServerSentEvent(
                    event=event.type,
                    data=event.model_dump_json()
                )
            # 7. End downstream trace span
            if downstream_span:
                try:
                    downstream_span.update(output={"response": full_response})
                    downstream_span.end()
                except Exception as e:
                    logger.warning("Failed to end Langfuse downstream span", error=str(e))
            # 8. Save session memory using thread pool executor
            await save_context(
                memory,
                {"input": request.message},
                {"output": full_response}
            )
        except Exception as e:
            status = "error"
            logger.error("Error in chat event generator", error=str(e))
            yield ServerSentEvent(
                event="error",
                data=ChatStreamEvent(
                    type="error",
                    error=f"Internal supervisor error: {str(e)}"
                ).model_dump_json()
            )
        finally:
            # 9. Close the root observation.
            #
            # v2 traces needed no closing; a v4 root span does -- an unended span
            # never exports, so skipping this loses the whole trace rather than
            # just its end time. It belongs in finally so an aborted stream or a
            # downstream error still yields a trace.
            if trace:
                try:
                    trace.update(output={"response": full_response, "status": status})
                    trace.end()
                except Exception as e:
                    logger.warning("Failed to end Langfuse root trace", error=str(e))
            # 10. Log request completion as structured JSON renderer
            total_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Request completed",
                correlation_id=correlation_id,
                intent=intent,
                downstream_service=downstream_service,
                total_ms=total_ms,
                status=status
            )
    return EventSourceResponse(event_generator())
@router.get("/sessions/{sessionId}/history", response_model=List[HistoryResponseItem])
async def session_history_endpoint(sessionId: str):
    """
    Retrieves the conversation history for a given session from Redis memory.
    """
    try:
        memory = get_session_memory(sessionId)
        memory_vars = await load_memory_variables(memory, {})
        history = memory_vars.get("history") or memory_vars.get("chat_history") or []
        
        formatted = []
        for msg in history:
            role = "user" if msg.type == "human" else "assistant"
            formatted.append(HistoryResponseItem(role=role, content=msg.content))
            
        return formatted
    except Exception as e:
        logger.error("Failed to load session history", session_id=sessionId, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load session history: {str(e)}"
        )
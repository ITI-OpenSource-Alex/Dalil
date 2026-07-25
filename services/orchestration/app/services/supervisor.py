import time
import structlog
from typing import Literal
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic
from langfuse.langchain import CallbackHandler
from app.core.config import settings


from app.core.metrics import (
    goa_orchestration_intent_classified_total,
    goa_orchestration_classification_latency_ms
)

logger = structlog.get_logger("orchestration.supervisor")


class IntentResult(BaseModel):
    intent: Literal["SPEAKING", "WRITING", "RAG", "OPPORTUNITY_SEARCH", "CV_REVIEW"]
    confidence: float
    is_fallback: bool = False

# Initialize ChatAnthropic and wrap it with structured output
llm = ChatAnthropic(
    model=settings.llm_model,
    anthropic_api_key=settings.anthropic_auth_token or settings.anthropic_api_key,
    **({"anthropic_api_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    default_headers={"User-Agent": settings.anthropic_user_agent} if settings.anthropic_user_agent else None,
    # ChatAnthropic 0.1.13 supports default_request_timeout, not timeout/max_retries.
    # Retry lives in classify_intent()'s explicit 2-attempt loop below.
    default_request_timeout=25.0,
)

# Monkeypatch to fix langchain_anthropic 0.1.13 bug where it assumes tools are beta
class _DummyBeta:
    pass

for client_attr in ("_client", "_async_client"):
    client_obj = getattr(llm, client_attr, None)
    if client_obj:
        if not hasattr(client_obj, "beta"):
            client_obj.beta = _DummyBeta()
        client_obj.beta.tools = client_obj

structured_llm = llm.with_structured_output(IntentResult, include_raw=True)


SUPERVISOR_PROMPT = """You are a routing agent. Classify the user message into exactly one of:
                        SPEAKING  - IELTS speaking practice or mock interview (e.g. "I want to practice speaking")
                        WRITING   - essay submission or writing evaluation (e.g. "Score my essay please")
                        RAG       - IELTS info, requirements, visa, scholarships (e.g. "What are the visa requirements?")
                        OPPORTUNITY_SEARCH - searching for study opportunities, scholarships, admissions (e.g. "Find me a scholarship in Germany")
                        CV_REVIEW - CV upload or improvement request (e.g. "Can you review my CV?")"""

async def classify_intent(message: str, trace_id: str = None, parent_span_id: str = None, user_id: str = "anonymous") -> IntentResult:
    """
    Classifies the user message intent into one of five categories.
    Traces the execution to Langfuse and records classification latency metrics.
    """
     
    messages = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        {"role": "user", "content": message}
    ]

    # Setup Langfuse callback handler if trace details are provided
    callbacks = []
    if settings.langfuse_public_key and settings.langfuse_secret_key and trace_id and parent_span_id:
        try:
            handler = CallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                trace_id=trace_id,
                parent_observation_id=parent_span_id
            )
            callbacks.append(handler)
        except Exception as e:
            logger.warning("Failed to initialize Langfuse callback handler", error=str(e))
    
    start_time = time.perf_counter()
    logger.info("Classifying intent using structured LLM...", message=message[:60])
    
    last_error = None
    for attempt in range(2):
        try:
            result_dict = await structured_llm.ainvoke(messages, config={"callbacks": callbacks})
            result = result_dict["parsed"]
            raw = result_dict["raw"]
            
            if result is None:
                last_error = ValueError("Structured output returned None")
                logger.warning("Structured output returned None, retrying once", message=message[:60])
                continue
                
            token_usage = raw.response_metadata.get("usage", {})
            input_tokens = getattr(token_usage, "input_tokens", 0)
            output_tokens = getattr(token_usage, "output_tokens", 0)
            if not input_tokens and isinstance(token_usage, dict):
                input_tokens = token_usage.get("input_tokens", 0)
                output_tokens = token_usage.get("output_tokens", 0)
                
            try:
                from app.telemetry import record_llm_cost
                record_llm_cost(user_id, settings.llm_model, input_tokens, output_tokens)
            except ImportError:
                pass
            
            if isinstance(result, dict):
                result = IntentResult(**result)
                
            # Record classification latency
            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_classification_latency_ms.observe(duration_ms)
            
            # Increment metric counter
            goa_orchestration_intent_classified_total.labels(intent=result.intent).inc()
            
            logger.info(
                "Classification completed",
                intent=result.intent,
                confidence=result.confidence,
                latency_ms=duration_ms
            )
            return result
            
        except Exception as e:
            last_error = e
            logger.warning("Intent classification error during attempt", error=str(e), attempt=attempt)

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.error("Intent classification failed after retries", error=str(last_error), latency_ms=duration_ms)
    logger.warning("Returning fallback intent due to classification failure", fallback_intent="RAG")
    # Fallback to RAG intent with low confidence in case of errors
    fallback = IntentResult(intent="RAG", confidence=0.0, is_fallback=True)
    goa_orchestration_intent_classified_total.labels(intent=fallback.intent).inc()
    return fallback
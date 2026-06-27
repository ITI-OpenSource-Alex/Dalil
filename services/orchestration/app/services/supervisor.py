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

# Initialize ChatAnthropic and wrap it with structured output
llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    anthropic_api_key=settings.anthropic_api_key
)
structured_llm = llm.with_structured_output(IntentResult)


SUPERVISOR_PROMPT = """You are a routing agent. Classify the user message into exactly one of:
                        SPEAKING  - IELTS speaking practice or mock interview
                        WRITING   - essay submission or writing evaluation
                        RAG       - IELTS info, requirements, visa, scholarships
                        OPPORTUNITY_SEARCH - searching for study opportunities, scholarships, admissions
                        CV_REVIEW - CV upload or improvement request"""

async def classify_intent(message: str, trace_id: str = None, parent_span_id: str = None) -> IntentResult:
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
    try:
        logger.info("Classifying intent using structured LLM...", message=message[:60])
        result = await structured_llm.ainvoke(messages, config={"callbacks": callbacks})
        
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
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error("Intent classification failed", error=str(e), latency_ms=duration_ms)
        # Fallback to RAG intent with low confidence in case of errors
        fallback = IntentResult(intent="RAG", confidence=0.0)
        goa_orchestration_intent_classified_total.labels(intent=fallback.intent).inc()
        return fallback
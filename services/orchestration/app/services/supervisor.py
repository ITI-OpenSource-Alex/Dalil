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
    intent: Literal[
        "SPEAKING", "WRITING", "RAG",
        "OPPORTUNITY_SEARCH", "CV_REVIEW", "EXAM_PREP",
    ]
    confidence: float
    is_fallback: bool = False
    # The user's message rewritten to stand on its own, with pronouns and
    # references resolved against the conversation so far.
    #
    # This rides along on the classification call rather than taking one of its
    # own. The remediation plan proposed a second LLM call to do the rewrite,
    # which would fix the same defect at the cost of another round trip on the
    # critical path of every chat turn -- and classification already costs 3-8s.
    # The supervisor is already reading the message and already returning
    # structured output, so asking it for one more field is free.
    #
    # Empty when there is no history to resolve against, and callers fall back
    # to the raw message.
    standalone_question: str = ""

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
                        CV_REVIEW - CV upload or improvement request (e.g. "Can you review my CV?")
                        EXAM_PREP - user wants to improve a skill, practice a section, or prepare for IELTS exam (e.g. "improve my reading score", "I want to practice listening", "help me with IELTS preparation")

You are also given the conversation so far. Use it for two things.

First, classify the LATEST message in the context of that conversation. "Is my
score high enough?" is RAG when it follows a question about entry requirements.

Second, set standalone_question: the latest message rewritten so it can be
understood with no conversation history at all. Resolve every pronoun and
reference ("it", "that one", "there", "the second one") into the thing it
refers to. Downstream services receive only this string and have no access to
the history, so anything you leave unresolved is lost.

Rules for standalone_question:
- Preserve the user's intent and specificity exactly. Do not answer, expand,
  correct, or add information that is not in the conversation.
- If the message already stands alone, copy it through unchanged.
- If there is no history, copy it through unchanged.

Example. History: "What IELTS band does the University of Potsdam Data Science
master require?" -> "It requires 6.5 overall." Latest: "Is my score high enough
for it?" -> standalone_question: "Is my IELTS score high enough for the
University of Potsdam Data Science master, which requires 6.5 overall?"
"""

EXAM_CONTEXT_INJECTION = """

--- USER EXAM PROFILE ---
The following IELTS exam data is verified from recent exam attempts:
- Reading Band: {ielts_reading_band}
- Listening Band: {ielts_listening_band}
- Writing Band: {ielts_writing_band}
- Speaking Band: {ielts_speaking_band}
- Identified Weak Area(s): {weak_areas}
- Last Exam Date: {last_exam_date}

PROACTIVE CONTEXT INSTRUCTIONS:
If the user's last exam revealed a specific weak area, you MUST proactively mention it and offer targeted practice tips — even when the user asks a general question. For example, if their weak area is "Speaking: Pronunciation", acknowledge this and suggest relevant practice.

EXAM_PREP RESPONSE RULES:
When the classified intent is EXAM_PREP, you MUST:
1. Reference the user's specific weak criterion from the profile above.
2. Suggest a specific Cambridge IELTS practice test (e.g. "Cambridge IELTS 18, Test 3, Reading Passage 2").
3. Provide a link to /exam for them to start a practice session.
4. Generic advice is FORBIDDEN — every response must be grounded in the user's actual exam data.
--- END EXAM PROFILE ---"""


def build_supervisor_prompt(exam_context: dict | None = None) -> str:
    """
    Constructs the full system prompt for the Supervisor Agent.

    When a valid exam profile is available (exam_count > 0), the prompt is
    enriched with the user's real IELTS data and additional behavioural
    instructions for proactive coaching and EXAM_PREP responses.
    """
    base = SUPERVISOR_PROMPT

    if not exam_context or exam_context.get("exam_count", 0) == 0:
        return base

    latest_bands = exam_context.get("latest_bands") or {}
    weak_areas_raw = exam_context.get("weak_areas") or {}

    weak_areas_str = ", ".join(
        f"{skill.title()}: {criterion}" for skill, criterion in weak_areas_raw.items()
    ) if weak_areas_raw else "None identified"

    enriched = base + EXAM_CONTEXT_INJECTION.format(
        ielts_reading_band=latest_bands.get("reading", "N/A"),
        ielts_listening_band=latest_bands.get("listening", "N/A"),
        ielts_writing_band=latest_bands.get("writing", "N/A"),
        ielts_speaking_band=latest_bands.get("speaking", "N/A"),
        weak_areas=weak_areas_str,
        last_exam_date=exam_context.get("last_exam_date", "N/A"),
    )
    return enriched


def _history_messages(history: list | None, limit: int = 6) -> list[dict]:
    """Render stored turns as chat messages for the supervisor.

    Trimmed to the most recent `limit` turns. The whole point is resolving
    references, which nearly always point at the last turn or two, so sending
    more would grow the token bill on every request to no benefit.
    """
    if not history:
        return []
    rendered = []
    for msg in history[-limit:]:
        role = "user" if getattr(msg, "type", None) == "human" else "assistant"
        content = getattr(msg, "content", None)
        if content:
            rendered.append({"role": role, "content": str(content)})
    return rendered


async def classify_intent(
    message: str,
    trace_id: str = None,
    parent_span_id: str = None,
    user_id: str = "anonymous",
    history: list | None = None,
    exam_context: dict | None = None,
) -> IntentResult:
    """
    Classifies the user message intent into one of six categories, rewrites
    it to stand alone against the conversation history, and uses exam context
    for personalised EXAM_PREP guidance.
    """

    system_prompt = build_supervisor_prompt(exam_context)

    messages = [
        {"role": "system", "content": system_prompt},
        *_history_messages(history),
        {"role": "user", "content": message},
    ]

    # Setup Langfuse callback handler if trace details are provided
    callbacks = []
    if settings.langfuse_public_key and settings.langfuse_secret_key and trace_id and parent_span_id:
        try:
            # v4's handler takes credentials from the process-wide client rather
            # than per-instance kwargs, and nests via trace_context. Passing the
            # v2 arguments raised "unexpected keyword argument 'secret_key'" into
            # the except below, so intent classification -- the one LLM call this
            # service makes directly -- was never traced (BUG-032).
            handler = CallbackHandler(
                trace_context={
                    "trace_id": trace_id,
                    "parent_span_id": parent_span_id,
                }
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
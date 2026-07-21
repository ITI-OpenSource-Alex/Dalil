import os
import time
import structlog
from langfuse.decorators import observe, langfuse_context
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field
from app.core.config import settings

logger = structlog.get_logger("rag_service.llm_boost")


class LLMBoostResult(BaseModel):
    boost_value: int = Field(
        description="An integer from -10 to +10 indicating the alignment of the CV with the program."
    )
    justification_tokens: str = Field(
        description="A short explanation of why this boost value was given."
    )


@observe(as_type="span", name="stage_3_llm_boost")
async def get_llm_boost(cv_text: str | None, program_description: str, user_id: str = "anonymous") -> dict:
    start_time = time.time()

    # 1. Graceful fast-path if no CV exists
    if not cv_text:
        return {
            "boost_value": 0,
            "justification_tokens": "No CV available.",
            "latency_ms": 0,
        }

    try:
        llm = ChatAnthropic(
            model_name=settings.llm_model,
            api_key=settings.anthropic_auth_token or settings.anthropic_api_key,
            **({"anthropic_api_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
            model_kwargs={"extra_headers": {"User-Agent": settings.anthropic_user_agent}},
            temperature=0.0,
            timeout=25.0,
            max_retries=1,
        )

        # Enforce structured output via Pydantic
        structured_llm = llm.with_structured_output(LLMBoostResult, include_raw=True)

        prompt = f"""
        You are an admissions expert. Evaluate the candidate's CV against the program requirements.
        Return a boost_value between -10 and +10, and a short justification.
        
        PROGRAM REQUIREMENTS:
        {program_description}
        
        CANDIDATE CV:
        {cv_text}
        """

        result_dict = await structured_llm.ainvoke(prompt)
        result = result_dict["parsed"]
        raw = result_dict["raw"]
        
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

        # 2. Safety clamp to strictly enforce the bounds
        clamped_boost = max(-10, min(10, result.boost_value))
        latency_ms = int((time.time() - start_time) * 1000)

        # 3. Inject trace data into Langfuse child span
        langfuse_context.update_current_span(
            metadata={
                "model": settings.llm_model,
                "boost_value": clamped_boost,
                "latency_ms": latency_ms,
            }
        )

        return {
            "boost_value": clamped_boost,
            "justification_tokens": result.justification_tokens,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        logger.error(f"LLM boost failed: {str(e)}")
        # Graceful fallback on LLM API failure
        return {
            "boost_value": 0,
            "justification_tokens": "LLM evaluation failed.",
            "latency_ms": int((time.time() - start_time) * 1000),
        }

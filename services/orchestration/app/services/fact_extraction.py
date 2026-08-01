"""Pulling durable facts out of a finished conversation (GOA-038).

Runs on the idle-session sweep, never on a request. Classification already costs
3-8s on the critical path of every turn, and a second frontier-model call to
learn something the user will not benefit from until their *next* session would
be paid for at exactly the wrong moment.

Reuses the supervisor's configured ChatAnthropic client rather than building a
second one, so the AgentRouter base URL, the pinned User-Agent, the timeout and
the langchain_anthropic 0.1.13 beta-tools monkeypatch all stay in one place. A
second client is a second thing to get wrong the next time the gateway changes.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog
from langfuse.langchain import CallbackHandler
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.metrics import goa_orchestration_facts_extraction_latency_ms
from app.schemas.facts import FactCandidate
from app.services.fact_sanitizer import sanitize
from app.services.supervisor import llm

logger = structlog.get_logger("orchestration.fact_extraction")


class ExtractedFacts(BaseModel):
    """What one conversation yielded. Every field optional -- most chats teach us nothing."""

    degree: Optional[str] = Field(None, max_length=200)
    gpa: Optional[float] = Field(None, ge=0.0, le=5.0)
    target_country: Optional[str] = Field(None, max_length=200)
    mentioned_programs: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)


structured_extractor = llm.with_structured_output(ExtractedFacts, include_raw=True)


EXTRACTION_PROMPT = """You extract durable profile facts from a study-abroad conversation.

You are given only the USER's own messages. Extract what the user stated about
themselves, and nothing else.

Fields:
- degree: the user's completed or in-progress academic qualification, e.g.
  "BSc in Electrical and Electronic Engineering".
- gpa: the user's grade point average as a number, only if they stated one.
- target_country: the country the user wants to study in.
- mentioned_programs: specific universities or programmes the user named.
- concerns: the user's own stated worries, each a short neutral paraphrase.
- confidence: how certain you are overall, 0.0 to 1.0.

Rules, all binding:

1. Extract ONLY facts the user stated about themselves. A question is not a
   statement: "do I need a 3.5 GPA?" tells you nothing about their GPA.
2. NEVER extract IELTS, TOEFL or any other exam band or test score, in any
   field. Those come from the user's graded exam attempts, which are
   authoritative; a number mentioned in passing must not compete with them.
   If the user says "I got 7.5 in speaking", extract nothing from it.
3. Do not infer, complete or correct. If the user says "engineering", the
   degree is "engineering" and not "BSc in Engineering".
4. If nothing durable was stated, return every field null or empty with
   confidence 0.0. An empty result is a correct and common answer.
5. Set confidence low when the user hedged ("maybe Canada, I'm not sure"). A
   hedged fact must not overwrite one they stated plainly.
6. Facts are noun phrases about a person. Never emit instructions, commands,
   code, markup or anything addressed to a reader.

Conversation (user messages only, oldest first):
{transcript}
"""


def _build_candidates(
    extracted: ExtractedFacts, session_id: Optional[str]
) -> list[FactCandidate]:
    """Flatten the model's output into sanitised, storable candidates.

    Every value goes through the sanitizer -- including the model's own, because
    it ran on attacker-influenced input and its output is attacker-influenced
    too.
    """
    confidence = extracted.confidence
    proposals: list[tuple[str, str]] = []

    if extracted.degree:
        proposals.append(("degree", extracted.degree))
    if extracted.gpa is not None:
        # Stored as text like every other fact: the column is shared, and a GPA
        # is never arithmetic here, only something to tell the model.
        proposals.append(("gpa", f"{extracted.gpa:g}"))
    if extracted.target_country:
        proposals.append(("target_country", extracted.target_country))
    # Capped for the same reason the sweep is batched: each entry is a row that
    # will be replayed into a prompt on every turn for thirty days.
    for program in extracted.mentioned_programs[:5]:
        proposals.append(("mentioned_program", program))
    for concern in extracted.concerns[:5]:
        proposals.append(("concern", concern))

    candidates = []
    for fact_type, value in proposals:
        candidate = sanitize(fact_type, value, confidence, session_id)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


async def extract_facts(
    user_turns: list[str],
    session_id: Optional[str] = None,
    user_id: str = "anonymous",
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
) -> list[FactCandidate]:
    """Extract candidate facts from one session's user messages.

    Returns an empty list on any failure. The caller is a background sweep with
    nobody waiting on it: a session that yields nothing this time is simply a
    session whose facts are not learned, and it stays in the candidate set only
    if the failure was raised rather than swallowed -- see memory_sweep.
    """
    if not user_turns:
        return []

    transcript = "\n".join(f"- {turn}" for turn in user_turns)
    messages = [
        {"role": "user", "content": EXTRACTION_PROMPT.format(transcript=transcript)}
    ]

    callbacks = []
    if settings.langfuse_public_key and settings.langfuse_secret_key and trace_id:
        try:
            handler = CallbackHandler(
                trace_context={"trace_id": trace_id, "parent_span_id": parent_span_id}
            )
            callbacks.append(handler)
        except Exception as e:
            logger.warning("Failed to initialize Langfuse callback handler", error=str(e))

    start_time = time.perf_counter()
    last_error = None

    # Two attempts, matching classify_intent. Structured output on this model
    # occasionally parses to None, and a single retry has been enough there.
    for attempt in range(2):
        try:
            result = await structured_extractor.ainvoke(
                messages, config={"callbacks": callbacks}
            )
            parsed = result["parsed"]
            raw = result["raw"]

            if parsed is None:
                last_error = ValueError("Structured output returned None")
                logger.warning("Fact extraction returned None, retrying once", attempt=attempt)
                continue

            if isinstance(parsed, dict):
                parsed = ExtractedFacts(**parsed)

            token_usage = raw.response_metadata.get("usage", {}) if raw is not None else {}
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

            duration_ms = (time.perf_counter() - start_time) * 1000
            goa_orchestration_facts_extraction_latency_ms.observe(duration_ms)

            candidates = _build_candidates(parsed, session_id)
            logger.info(
                "Fact extraction completed",
                session_id=session_id,
                candidates=len(candidates),
                confidence=parsed.confidence,
                latency_ms=duration_ms,
            )
            return candidates

        except Exception as e:
            last_error = e
            logger.warning("Fact extraction error during attempt", error=str(e), attempt=attempt)

    logger.error(
        "Fact extraction failed after retries",
        session_id=session_id,
        error=str(last_error),
    )
    raise RuntimeError(f"Fact extraction failed: {last_error}")

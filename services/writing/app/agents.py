import asyncio
import base64
import logging
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, TypeVar

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from pydantic import BaseModel, Field, ValidationError

from goa_pricing import cost_usd as price_call
from goa_security import wrap_untrusted

from app.config import get_settings
from app.metrics import UNPRICED_MODEL_TOTAL
from app.ocr_normalization import InputSource, NormalizedEssay, normalize_essay
from app.schemas import CriterionEvaluation, InlineIssue
from app.writing_rubric import allowed_descriptor_ids, render_descriptors

logger = logging.getLogger(__name__)

# Total attempts (not retries) to obtain a parseable answer from one criterion
# agent. Measured prose-instead-of-JSON rate against AgentRouter is roughly 1 in
# 6 per agent; evaluation.py fails the whole submission if any one of the four
# agents fails, so p(task fails) is ~1 - (1 - r**attempts)**4. At 2 attempts
# that is ~11%, at 3 it is ~2%. Three is the point where a candidate is not
# routinely told their essay could not be marked. See _execute.
_AGENT_PARSE_ATTEMPTS = int(os.getenv("WRITING_AGENT_PARSE_ATTEMPTS", "3"))


Criterion = Literal["task_response", "cohesion", "vocabulary", "grammar"]
CRITERIA: tuple[Criterion, ...] = (
    "task_response",
    "cohesion",
    "vocabulary",
    "grammar",
)

CRITERION_PROMPTS: dict[Criterion, str] = {
    "task_response": (
        "Assess how completely and accurately the response addresses the IELTS task, "
        "develops a clear position, and supports its main ideas."
    ),
    "cohesion": (
        "Assess organisation, paragraphing, logical progression, referencing, and the "
        "natural and accurate use of cohesive devices."
    ),
    "vocabulary": (
        "Assess lexical range, precision, collocation, spelling, word formation, and "
        "the ability to convey exact meaning without repetition."
    ),
    "grammar": (
        "Assess grammatical range and accuracy, sentence forms, punctuation, and the "
        "effect errors have on clarity."
    ),
}

TaskNumber = Literal[1, 2]

TASK1_ACADEMIC_INSTRUCTIONS = (
    "This is IELTS Academic Writing Task 1: the candidate must summarise, describe, "
    "and compare data from a chart, graph, table, or diagram in at least 150 words. "
    "For Task Response specifically, check for a clear overview of the main trends, "
    "accurate reporting of key figures against the supplied chart description, and "
    "appropriate comparisons. The candidate must NOT give opinions or explain reasons "
    "behind the data — penalise Task Response if they do."
)

TASK1_GENERAL_INSTRUCTIONS = (
    "This is IELTS General Training Writing Task 1: a letter of at least 150 words "
    "written for a specified purpose. For Task Response, check that the letter fully "
    "covers all three bullet points in the prompt, and that its tone matches the "
    "specified recipient: informal (friend/family), semi-formal (someone known but "
    "not close), or formal (unknown/official recipient). For Cohesion, verify the "
    "letter has an appropriate opening greeting (e.g. 'Dear ...') and closing that "
    "match the required register — 'Yours sincerely' for a named recipient, 'Yours "
    "faithfully' for 'Dear Sir/Madam', or a casual sign-off for an informal letter. "
    "Penalise Cohesion if the greeting/closing register is mismatched or missing."
)

TASK2_INSTRUCTIONS = (
    "This is IELTS Writing Task 2: a formal essay of at least 250 words responding "
    "to a point of view, argument, or problem. For Task Response, check that the "
    "candidate presents a clear position, addresses all parts of the question, and "
    "supports ideas with relevant examples and explanation."
)


def _task_instructions(exam_type: str, task_number: int) -> str:
    if task_number == 1:
        if exam_type.strip().lower() in {"general", "general_training", "gt"}:
            return TASK1_GENERAL_INSTRUCTIONS
        return TASK1_ACADEMIC_INSTRUCTIONS
    return TASK2_INSTRUCTIONS

SCORE_SYSTEM_PROMPT = """You are a strict JSON API. You MUST output ONLY valid JSON. Do not
include any extended thinking, reasoning blocks, or conversational text. Start your
response immediately with { and end with }.

You are a certified IELTS Writing examiner. Evaluate only the requested criterion
against the complete frozen descriptor ladder supplied in the request.

Use best-fit scoring. Do not default downward. Select the descriptor that best
represents the response as a whole, then explicitly test that decision against the
immediately higher and lower bands. A half band is allowed only when the evidence is
genuinely balanced between two adjacent integer descriptors. Judge the normalized
candidate language; never discuss handwriting, OCR, image quality, or normalization.

Return one JSON object and no markdown with this exact shape:
{
  "band_score": 0.0,
  "descriptor_id": "criterion.integer-band",
  "confidence": "high|medium|low",
  "borderline": false,
  "evidence": ["specific essay evidence 1", "specific essay evidence 2"],
  "lower_band_comparison": "why the response exceeds, or does not exceed, the adjacent lower band",
  "higher_band_comparison": "why the response meets, or does not meet, the adjacent higher band"
}

Use an IELTS band from 0 to 9. descriptor_id must be one supplied in the request;
for a half band cite the lower of the two adjacent integer descriptor ids. Evidence
must be concrete and criterion-specific. Set borderline=true only when two adjacent
bands are genuinely similarly supported. Confidence is low only when the submitted
text does not provide enough evidence for a stable decision.

Output format is absolute. Your entire reply must be the JSON object and nothing
else: begin with `{` and end with `}`. Never emit a markdown heading, a `**Band
score**` line, bullet points, a preamble such as "Here is my assessment", or any
prose outside the JSON. A reply that opens with `#` or `**` is a failed response."""


FEEDBACK_SYSTEM_PROMPT = """You are a strict JSON API and an IELTS Writing coach.
Return only one JSON object, starting with { and ending with }. Do not rescore the
essay. The criterion bands in the request are frozen decisions from separate scoring
agents. Produce concise, criterion-specific coaching grounded in the submitted text.

Return this exact shape:
{
  "evaluations": [
    {
      "criterion": "task_response|cohesion|vocabulary|grammar",
      "feedback": "criterion-specific summary consistent with the frozen band",
      "improvement_tip": "one actionable improvement",
      "sentence_examples": ["example 1", "example 2", "example 3"],
      "highlighted_issues": [
        {"text": "exact normalized essay substring", "issue_type": "specific type", "suggestion": "specific revision"}
      ]
    }
  ]
}

Return exactly one entry for every requested criterion and no others. Each entry must
have exactly three sentence-level examples quoting short portions of the essay. Every
issue text must be an exact, case-sensitive substring of the normalized essay. Do not
invent issues to fill the list. Never mention OCR, normalization, handwriting, image
quality, model decisions, or hidden scoring evidence."""


class RawIssue(BaseModel):
    text: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)# Changed from 'issue' according to GOA-68 requirements    
    suggestion: str = Field(min_length=1)


class RawScoreResponse(BaseModel):
    # Clamp at the service boundary. A malformed out-of-range model value must
    # not leak to the API, but it also should not trigger three paid retries.
    band_score: float
    descriptor_id: str = Field(min_length=3)
    confidence: Literal["high", "medium", "low"]
    borderline: bool = False
    evidence: list[str] = Field(min_length=2)
    lower_band_comparison: str = Field(min_length=1)
    higher_band_comparison: str = Field(min_length=1)


class RawCriterionFeedback(BaseModel):
    criterion: Criterion
    feedback: str = Field(min_length=1)
    improvement_tip: str = Field(min_length=1)
    sentence_examples: list[str] = Field(min_length=3)
    highlighted_issues: list[RawIssue] = Field(default_factory=list)


class RawFeedbackResponse(BaseModel):
    evaluations: list[RawCriterionFeedback] = Field(min_length=1)


@dataclass(frozen=True)
class AgentExecution:
    result: CriterionEvaluation
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    # None when the model is absent from the shared price table (GOA-135).
    # Deliberately not defaulted to 0.0: "we could not price this call" and "this
    # call was free" must stay distinguishable, or a pricing gap looks like an
    # idle service. Aggregators skip None rather than coercing it.
    cost_usd: float | None


@dataclass(frozen=True)
class ScoreExecution:
    criterion: Criterion
    decision: RawScoreResponse
    band_score: float
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float | None
    model_calls: int
    ensemble_used: bool


@dataclass(frozen=True)
class FeedbackExecution:
    evaluations: dict[Criterion, RawCriterionFeedback]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float | None
    model_calls: int


def _round_to_half(value: float) -> float:
    return max(0.0, min(9.0, int(value * 2 + 0.5) / 2))


def _json_object(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Writing agent did not return a JSON object")
    return cleaned[start : end + 1]


def _response_text(response: Any) -> str:
    parts = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise ValueError("Writing agent returned no text content")
    return "".join(parts)


def _annotate_issues(essay: NormalizedEssay, issues: list[RawIssue]) -> list[InlineIssue]:
    annotated: list[InlineIssue] = []
    for item in issues:
        start = essay.text.find(item.text)
        if start < 0:
            continue
        original_start, original_end = essay.original_span(start, start + len(item.text))
        annotated.append(
            InlineIssue(
                text=essay.original_text[original_start:original_end],
                issue_type=item.issue_type,
                suggestion=item.suggestion,
                start_char=original_start,
                end_char=original_end,
            )
        )
    return annotated

def _s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.aws_endpoint_url,
    )


def calculate_word_count(text: str) -> int:
    """Accurately count words handling multiple spaces and punctuation."""
    return len(re.findall(r'\b\w+\b', text))
async def _fetch_chart_bytes(s3_key: str) -> bytes:
    settings = get_settings()

    def _get() -> bytes:
        try:
            obj = _s3_client().get_object(Bucket=settings.s3_bucket, Key=s3_key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in {"NoSuchKey", "404"}:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Stimulus image not found for key '{s3_key}'",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unable to fetch stimulus image: {error_code or 'S3 error'}",
            ) from exc
        return obj["Body"].read()

    # boto3 is sync; keep it off the event loop.
    return await asyncio.to_thread(_get)


def _vision_span(
    trace: Any,
    *,
    model: str,
    s3_key: str,
    media_type: str,
) -> Any:
    if trace is None:
        return None
    try:
        return trace.start_observation(
            name="writing-vision-stimulus",
            as_type="generation",
            model=model,
            input={"s3_key": s3_key, "media_type": media_type},
        )
    except Exception:
        return None


def _end_vision_span(span: Any, *, description: str, usage: Any) -> None:
    if span is None:
        return
    try:
        span.update(
            output=description,
            usage_details={
                "input": getattr(usage, "input_tokens", 0),
                "output": getattr(usage, "output_tokens", 0),
            },
        )
        span.end()
    except Exception:
        pass


def _fail_vision_span(span: Any, exc: BaseException) -> None:
    if span is None:
        return
    try:
        span.update(
            level="ERROR",
            status_message=str(exc),
            output={"error": str(exc)},
        )
        span.end()
    except Exception:
        pass


async def extract_chart_context(s3_key: str, *, trace: Any = None) -> str:
    """
    Fetches an IELTS Task 1 (Academic) stimulus image from S3 and asks the
    configured Claude vision model for a neutral, factual description, so the
    Claude-based examiner can verify the candidate's data accuracy without
    needing vision input itself.

    `trace` is the caller's Langfuse observation. When supplied, the vision call
    gets its own generation child span so the single multimodal request is
    attributed separately from the four criterion agents (GOA-093).
    """
    import logging
    from anthropic import AsyncAnthropic

    settings = get_settings()
    key = settings.anthropic_api_key
    if not key or key == "not-configured":
        logging.getLogger(__name__).warning("ANTHROPIC_API_KEY is not configured or missing, using placeholder.")
        key = "not-configured"

    image_bytes = await _fetch_chart_bytes(s3_key)
    encoded_image = base64.b64encode(image_bytes).decode("ascii")

    media_type = "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        media_type = "image/jpeg"
    elif image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        media_type = "image/gif"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        media_type = "image/webp"

    client = AsyncAnthropic(
        api_key=key,
        timeout=settings.anthropic_timeout_seconds,
        default_headers={"User-Agent": settings.anthropic_user_agent},
        **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    )

    span = _vision_span(
        trace,
        model=settings.vision_model,
        s3_key=s3_key,
        media_type=media_type,
    )

    try:
        response = await client.messages.create(
            model=settings.vision_model,
            # No `temperature`. The gateway fronts Bedrock, which rejects the parameter
            # outright for this model:
            #   ValidationException: `temperature` is deprecated for this model
            # It surfaced as an intermittent 502 ("2 of 4 writing agents failed") because
            # only some requests land on the backend that enforces it — the same erratic
            # routing seen elsewhere on this gateway. Determinism now comes from the
            # rubric and the JSON schema, not from a sampling parameter.
            #
            # opus-4-8 is an extended-thinking model: at 500 the ThinkingBlock alone
            # exhausted the budget (stop_reason='max_tokens', a single ThinkingBlock
            # and no text), so no chart description was emitted and _response_text
            # raised "no text content" — a fast raw 500 before the grading swarm even
            # started. The text prompt below now forbids reasoning blocks, and 4000
            # leaves ample room for the factual chart description.
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": "You are a strict text API. Do not include any extended thinking, reasoning blocks, or conversational preamble. Start immediately with the factual chart description. You objectively describe IELTS Writing Task 1 (Academic) stimulus images (line/bar charts, pie charts, tables, or process diagrams) so an examiner who cannot see the image can verify the candidate's data accuracy. List the exact axis labels, units, categories, and key data points/trends visible in the image. Do not evaluate or judge; describe only, factually and neutrally.\n\nDescribe this IELTS Task 1 chart/graph/table/diagram.",
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        _fail_vision_span(span, exc)
        raise

    # Extended-thinking Claude Opus backends via the gateway can prepend a
    # ThinkingBlock, which has no `.text`, so response.content[0] is not the
    # answer. _response_text iterates every block and keeps only the text ones —
    # the same reader the grading agents use.
    description = _response_text(response).strip()
    _end_vision_span(span, description=description, usage=getattr(response, "usage", None))
    return description

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(frozen=True)
class _ModelCall:
    parsed: BaseModel
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float | None
    attempts: int


def _sum_costs(*costs: float | None) -> float | None:
    return None if any(cost is None for cost in costs) else sum(costs)  # type: ignore[arg-type]


class WritingAgentRunner:
    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_tokens: int = 16000,
        score_max_tokens: int = 8000,
        feedback_max_tokens: int = 8000,
        feedback_model: str | None = None,
        selective_ensemble: bool = True,
        max_ensemble_criteria: int = 1,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.score_max_tokens = score_max_tokens
        self.feedback_max_tokens = feedback_max_tokens
        self.feedback_model = feedback_model or model
        self.selective_ensemble = selective_ensemble
        self.max_ensemble_criteria = max(0, max_ensemble_criteria)

    async def _call_json(
        self,
        *,
        response_model: type[ResponseModel],
        system: str,
        prompt: str,
        max_tokens: int,
        label: str,
        user_id: str,
        model: str | None = None,
    ) -> _ModelCall:
        started = time.perf_counter()
        parsed: ResponseModel | None = None
        last_error: Exception | None = None
        prompt_tokens = 0
        completion_tokens = 0
        costs: list[float | None] = []
        selected_model = model or self.model
        effective_prompt = system + "\n\n---\n\n" + prompt

        for attempt in range(_AGENT_PARSE_ATTEMPTS):
            response = await self.client.messages.create(
                model=selected_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": effective_prompt}],
            )
            usage = getattr(response, "usage", None)
            call_prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            call_completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            prompt_tokens += call_prompt_tokens
            completion_tokens += call_completion_tokens
            cost = price_call(selected_model, call_prompt_tokens, call_completion_tokens)
            costs.append(cost)
            if cost is None:
                UNPRICED_MODEL_TOTAL.labels(model=selected_model).inc()
            try:
                from app.telemetry import record_llm_cost

                record_llm_cost(
                    user_id, selected_model, call_prompt_tokens, call_completion_tokens
                )
            except ImportError:
                pass

            if getattr(response, "stop_reason", None) == "max_tokens":
                raise ValueError(
                    f"Writing {label} hit the max_tokens ceiling; its JSON is truncated."
                )
            try:
                parsed = response_model.model_validate_json(
                    _json_object(_response_text(response))
                )
                break
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.warning(
                    "Writing %s returned invalid JSON on attempt %d/%d: %s",
                    label,
                    attempt + 1,
                    _AGENT_PARSE_ATTEMPTS,
                    str(exc)[:200],
                )

        if parsed is None:
            raise ValueError(
                f"Writing {label} did not return valid JSON after "
                f"{_AGENT_PARSE_ATTEMPTS} attempts: {last_error}"
            ) from last_error
        return _ModelCall(
            parsed=parsed,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=(time.perf_counter() - started) * 1000,
            cost_usd=_sum_costs(*costs),
            attempts=len(costs),
        )

    def _score_prompt(
        self,
        criterion: Criterion,
        essay: NormalizedEssay,
        exam_type: str,
        task_number: TaskNumber,
        *,
        task_prompt: str | None,
        chart_context: str | None,
        reviewer_instruction: str,
    ) -> tuple[str, str]:
        task_instructions = _task_instructions(exam_type, task_number)
        system = (
            SCORE_SYSTEM_PROMPT
            + "\n\nCriterion-specific instruction: "
            + CRITERION_PROMPTS[criterion]
            + "\n\n"
            + render_descriptors(criterion, task_number)
        )
        sections = [
            reviewer_instruction,
            f"IELTS exam type: {exam_type}",
            f"Task number: {task_number}",
            f"Criterion: {criterion}",
            f"Task instruction: {task_instructions}",
        ]
        if task_prompt:
            sections.append(
                wrap_untrusted(
                    task_prompt,
                    label="TASK QUESTION",
                    origin="the exam question supplied to the candidate",
                )
            )
        if chart_context:
            sections.append(
                wrap_untrusted(
                    chart_context,
                    label="STIMULUS DESCRIPTION",
                    origin="a vision extraction of the official Task 1 stimulus",
                )
            )
        sections.append(
            wrap_untrusted(
                essay.text,
                label="NORMALIZED CANDIDATE ESSAY",
                origin="a candidate submission with deterministic OCR artifacts removed",
            )
        )
        return system, "\n\n".join(sections)

    async def _score_once(
        self,
        criterion: Criterion,
        essay: NormalizedEssay,
        exam_type: str,
        task_number: TaskNumber,
        *,
        user_id: str,
        task_prompt: str | None,
        chart_context: str | None,
        reviewer_instruction: str,
    ) -> _ModelCall:
        system, prompt = self._score_prompt(
            criterion,
            essay,
            exam_type,
            task_number,
            task_prompt=task_prompt,
            chart_context=chart_context,
            reviewer_instruction=reviewer_instruction,
        )
        call = await self._call_json(
            response_model=RawScoreResponse,
            system=system,
            prompt=prompt,
            max_tokens=self.score_max_tokens,
            label=f"score agent for '{criterion}'",
            user_id=user_id,
        )
        parsed = call.parsed
        assert isinstance(parsed, RawScoreResponse)
        if parsed.descriptor_id not in allowed_descriptor_ids(criterion, task_number):
            raise ValueError(
                f"Writing score agent for '{criterion}' cited unknown descriptor "
                f"'{parsed.descriptor_id}'"
            )
        return call

    async def score(
        self,
        criterion: Criterion,
        essay: NormalizedEssay,
        exam_type: str,
        *,
        task_number: TaskNumber = 2,
        user_id: str = "anonymous",
        chart_context: str | None = None,
        task_prompt: str | None = None,
        allow_ensemble: bool = True,
        primary_execution: ScoreExecution | None = None,
    ) -> ScoreExecution:
        started = time.perf_counter()
        calls: list[_ModelCall] = []
        if primary_execution is None:
            calls.append(
                await self._score_once(
                    criterion,
                    essay,
                    exam_type,
                    task_number,
                    user_id=user_id,
                    task_prompt=task_prompt,
                    chart_context=chart_context,
                    reviewer_instruction="Act as the primary independent examiner.",
                )
            )
            primary = calls[0].parsed
            assert isinstance(primary, RawScoreResponse)
            base_prompt_tokens = 0
            base_completion_tokens = 0
            base_latency_ms = 0.0
            base_cost: float | None = 0.0
            base_model_calls = 0
        else:
            if primary_execution.criterion != criterion:
                raise ValueError("primary score criterion does not match review criterion")
            primary = primary_execution.decision
            base_prompt_tokens = primary_execution.prompt_tokens
            base_completion_tokens = primary_execution.completion_tokens
            base_latency_ms = primary_execution.latency_ms
            base_cost = primary_execution.cost_usd
            base_model_calls = primary_execution.model_calls

        decision = primary
        ensemble_used = allow_ensemble and self.selective_ensemble and (
            primary.confidence == "low" or primary.borderline
        )

        if ensemble_used:
            secondary_call = await self._score_once(
                criterion,
                essay,
                exam_type,
                task_number,
                user_id=user_id,
                task_prompt=task_prompt,
                chart_context=chart_context,
                reviewer_instruction=(
                    "Act as a second independent examiner. Do not assume another "
                    "examiner's score; make a fresh descriptor-based decision."
                ),
            )
            calls.append(secondary_call)
            secondary = secondary_call.parsed
            assert isinstance(secondary, RawScoreResponse)
            difference = abs(primary.band_score - secondary.band_score)
            if difference <= 0.5:
                combined = _round_to_half(
                    (primary.band_score + secondary.band_score) / 2
                )
                source = primary if primary.confidence != "low" else secondary
                decision = source.model_copy(
                    update={
                        "band_score": combined,
                        "confidence": "medium" if difference else source.confidence,
                        "borderline": difference > 0,
                    }
                )
            else:
                packets = (
                    "Two independent examiners disagreed. Resolve the score from the "
                    "essay and frozen descriptors; do not average mechanically.\n"
                    f"EXAMINER A: {primary.model_dump_json()}\n"
                    f"EXAMINER B: {secondary.model_dump_json()}"
                )
                adjudication_call = await self._score_once(
                    criterion,
                    essay,
                    exam_type,
                    task_number,
                    user_id=user_id,
                    task_prompt=task_prompt,
                    chart_context=chart_context,
                    reviewer_instruction=packets,
                )
                calls.append(adjudication_call)
                adjudicated = adjudication_call.parsed
                assert isinstance(adjudicated, RawScoreResponse)
                decision = adjudicated

        costs = [call.cost_usd for call in calls]
        return ScoreExecution(
            criterion=criterion,
            decision=decision,
            band_score=_round_to_half(decision.band_score),
            prompt_tokens=base_prompt_tokens
            + sum(call.prompt_tokens for call in calls),
            completion_tokens=base_completion_tokens
            + sum(call.completion_tokens for call in calls),
            latency_ms=base_latency_ms + (time.perf_counter() - started) * 1000,
            cost_usd=_sum_costs(base_cost, *costs),
            model_calls=base_model_calls + sum(call.attempts for call in calls),
            ensemble_used=ensemble_used,
        )

    async def generate_feedback(
        self,
        essay: NormalizedEssay,
        scores: dict[Criterion, ScoreExecution],
        exam_type: str,
        *,
        task_number: TaskNumber = 2,
        user_id: str = "anonymous",
        task_prompt: str | None = None,
    ) -> FeedbackExecution:
        score_packets = {
            criterion: {
                "frozen_band": score.band_score,
                "descriptor_id": score.decision.descriptor_id,
                "evidence": score.decision.evidence,
                "lower_band_comparison": score.decision.lower_band_comparison,
                "higher_band_comparison": score.decision.higher_band_comparison,
            }
            for criterion, score in scores.items()
        }
        sections = [
            f"IELTS exam type: {exam_type}",
            f"Task number: {task_number}",
            f"Requested criteria: {', '.join(scores)}",
            "Frozen scoring packets (do not change these bands):\n"
            + __import__("json").dumps(score_packets, ensure_ascii=False),
        ]
        if task_prompt:
            sections.append(
                wrap_untrusted(
                    task_prompt,
                    label="TASK QUESTION",
                    origin="the exam question supplied to the candidate",
                )
            )
        sections.append(
            wrap_untrusted(
                essay.text,
                label="NORMALIZED CANDIDATE ESSAY",
                origin="a candidate submission with deterministic OCR artifacts removed",
            )
        )
        call = await self._call_json(
            response_model=RawFeedbackResponse,
            system=FEEDBACK_SYSTEM_PROMPT,
            prompt="\n\n".join(sections),
            max_tokens=self.feedback_max_tokens,
            label="feedback agent",
            user_id=user_id,
            model=self.feedback_model,
        )
        parsed = call.parsed
        assert isinstance(parsed, RawFeedbackResponse)
        by_criterion = {item.criterion: item for item in parsed.evaluations}
        if set(by_criterion) != set(scores) or len(parsed.evaluations) != len(scores):
            raise ValueError(
                "Writing feedback agent did not return exactly the requested criteria"
            )
        return FeedbackExecution(
            evaluations=by_criterion,
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            latency_ms=call.latency_ms,
            cost_usd=call.cost_usd,
            model_calls=call.attempts,
        )

    def build_evaluation(
        self,
        essay: NormalizedEssay,
        score: ScoreExecution,
        raw: RawCriterionFeedback,
    ) -> CriterionEvaluation:
        feedback = raw.feedback.rstrip() + "\n\nSentence-level examples:\n" + "\n".join(
            f"{index}. {example}"
            for index, example in enumerate(raw.sentence_examples[:3], start=1)
        )
        return CriterionEvaluation(
            criterion=score.criterion,
            band_score=score.band_score,
            feedback=feedback,
            improvement_tip=raw.improvement_tip,
            word_count=calculate_word_count(essay.text),
            inline_issues=_annotate_issues(essay, raw.highlighted_issues),
        )

    async def evaluate(
        self,
        criterion: Criterion,
        essay_text: str,
        exam_type: str,
        user_id: str = "anonymous",
        *,
        input_source: InputSource = "typed",
    ) -> AgentExecution:
        essay = normalize_essay(essay_text, input_source)
        task_number: TaskNumber = 1 if "task_1" in exam_type or "task1" in exam_type else 2
        score = await self.score(
            criterion, essay, exam_type, task_number=task_number, user_id=user_id
        )
        feedback = await self.generate_feedback(
            essay,
            {criterion: score},
            exam_type,
            task_number=task_number,
            user_id=user_id,
        )
        return AgentExecution(
            result=self.build_evaluation(
                essay, score, feedback.evaluations[criterion]
            ),
            prompt_tokens=score.prompt_tokens + feedback.prompt_tokens,
            completion_tokens=score.completion_tokens + feedback.completion_tokens,
            latency_ms=score.latency_ms + feedback.latency_ms,
            cost_usd=_sum_costs(score.cost_usd, feedback.cost_usd),
        )

    async def evaluate_exam_task(
        self,
        criterion: Criterion,
        essay_text: str,
        exam_type: str,
        task_number: TaskNumber,
        user_id: str = "anonymous",
        chart_context: str | None = None,
        task_prompt: str | None = None,
        input_source: InputSource = "typed",
    ) -> AgentExecution:
        essay = normalize_essay(essay_text, input_source)
        score = await self.score(
            criterion,
            essay,
            exam_type,
            task_number=task_number,
            user_id=user_id,
            chart_context=chart_context,
            task_prompt=task_prompt,
        )
        feedback = await self.generate_feedback(
            essay,
            {criterion: score},
            exam_type,
            task_number=task_number,
            user_id=user_id,
            task_prompt=task_prompt,
        )
        return AgentExecution(
            result=self.build_evaluation(
                essay, score, feedback.evaluations[criterion]
            ),
            prompt_tokens=score.prompt_tokens + feedback.prompt_tokens,
            completion_tokens=score.completion_tokens + feedback.completion_tokens,
            latency_ms=score.latency_ms + feedback.latency_ms,
            cost_usd=_sum_costs(score.cost_usd, feedback.cost_usd),
        )


@lru_cache
def get_agent_runner() -> WritingAgentRunner:
    from anthropic import AsyncAnthropic
    import logging

    settings = get_settings()
    
    key = settings.anthropic_api_key
    if not key or key == "not-configured":
        logging.getLogger(__name__).warning("ANTHROPIC_API_KEY is not configured or missing, using placeholder.")
        key = "not-configured"

    client = AsyncAnthropic(
        api_key=key,
        timeout=settings.anthropic_timeout_seconds,
        default_headers={"User-Agent": settings.anthropic_user_agent},
        **({"base_url": settings.anthropic_base_url} if settings.anthropic_base_url else {}),
    )
    return WritingAgentRunner(
        client,
        model=settings.writing_model,
        max_tokens=settings.writing_agent_max_tokens,
        score_max_tokens=settings.writing_score_max_tokens,
        feedback_max_tokens=settings.writing_feedback_max_tokens,
        feedback_model=settings.writing_feedback_model,
        selective_ensemble=settings.writing_selective_ensemble,
        max_ensemble_criteria=settings.writing_max_ensemble_criteria,
    )


async def _public_evaluation(
    criterion: Criterion,
    essay_text: str,
    exam_type: str,
    runner: WritingAgentRunner | None,
    user_id: str = "anonymous",
) -> dict[str, Any]:
    execution = await (runner or get_agent_runner()).evaluate(
        criterion, essay_text, exam_type, user_id=user_id
    )
    return execution.result.model_dump()


async def evaluate_task_response(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None, user_id: str = "anonymous"
) -> dict[str, Any]:
    return await _public_evaluation("task_response", essay_text, exam_type, runner, user_id)


async def evaluate_cohesion(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None, user_id: str = "anonymous"
) -> dict[str, Any]:
    return await _public_evaluation("cohesion", essay_text, exam_type, runner, user_id)


async def evaluate_vocabulary(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None, user_id: str = "anonymous"
) -> dict[str, Any]:
    return await _public_evaluation("vocabulary", essay_text, exam_type, runner, user_id)


async def evaluate_grammar(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None, user_id: str = "anonymous"
) -> dict[str, Any]:
    return await _public_evaluation("grammar", essay_text, exam_type, runner, user_id)

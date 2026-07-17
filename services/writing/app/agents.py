import json
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import boto3
import httpx

from pydantic import BaseModel, Field

from app.config import get_settings
from app.schemas import CriterionEvaluation, HighlightedIssue


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

SYSTEM_PROMPT = """You are a certified IELTS Writing examiner. Apply the public IELTS
Writing band descriptors conservatively and evaluate only the requested criterion.
The input is computer-typed text; never discuss handwriting, OCR, or image quality.

Return one JSON object and no markdown with this exact shape:
{
  "band_score": 0.0,
  "feedback": "criterion-specific summary",
  "sentence_examples": [
    "specific example and explanation 1",
    "specific example and explanation 2",
    "specific example and explanation 3"
  ],
  "highlighted_issues": [
    {"text": "exact verbatim substring from the essay", "issue": "what is wrong", "suggestion": "specific replacement or revision"}
  ]
}

Use an IELTS band from 0 to 9. sentence_examples must contain exactly three specific,
sentence-level examples quoting short portions of the submitted essay. Every issue text
must be an exact, case-sensitive substring of the essay so character offsets can be
computed. Do not invent an issue merely to fill the list."""


class RawIssue(BaseModel):
    text: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)


class RawAgentResponse(BaseModel):
    band_score: float
    feedback: str = Field(min_length=1)
    sentence_examples: list[str] = Field(min_length=3, max_length=3)
    highlighted_issues: list[RawIssue] = Field(default_factory=list)


@dataclass(frozen=True)
class AgentExecution:
    result: CriterionEvaluation
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float


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


def _annotate_issues(essay_text: str, issues: list[RawIssue]) -> list[HighlightedIssue]:
    annotated: list[HighlightedIssue] = []
    for item in issues:
        start = essay_text.find(item.text)
        if start < 0:
            continue
        annotated.append(
            HighlightedIssue(
                text=item.text,
                issue=item.issue,
                suggestion=item.suggestion,
                start=start,
                end=start + len(item.text),
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


async def _fetch_chart_bytes(s3_key: str) -> bytes:
    settings = get_settings()

    def _get() -> bytes:
        obj = _s3_client().get_object(Bucket=settings.s3_bucket, Key=s3_key)
        return obj["Body"].read()

    # boto3 is sync; keep it off the event loop.
    return await asyncio.to_thread(_get)


async def extract_chart_context(s3_key: str) -> str:
    """
    Fetches an IELTS Task 1 (Academic) stimulus image from S3 and asks gpt-4o
    for a neutral, factual description, so the Claude-based examiner can verify
    the candidate's data accuracy without needing vision input itself.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    image_bytes = await _fetch_chart_bytes(s3_key)
    encoded_image = base64.b64encode(image_bytes).decode("ascii")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "temperature": 0,
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You objectively describe IELTS Writing Task 1 (Academic) "
                            "stimulus images (line/bar charts, pie charts, tables, or "
                            "process diagrams) so an examiner who cannot see the image "
                            "can verify the candidate's data accuracy. List the exact "
                            "axis labels, units, categories, and key data points/trends "
                            "visible in the image. Do not evaluate or judge; describe "
                            "only, factually and neutrally."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this IELTS Task 1 chart/graph/table/diagram.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{encoded_image}"},
                            },
                        ],
                    },
                ],
            },
        )
    response.raise_for_status()
    payload = response.json()
    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ValueError("Unexpected response shape from gpt-4o") from exc

class WritingAgentRunner:
    def __init__(self, client: Any, *, model: str) -> None:
        self.client = client
        self.model = model

    async def evaluate(
        self,
        criterion: Criterion,
        essay_text: str,
        exam_type: str,
    ) -> AgentExecution:
        prompt = (
            f"IELTS exam/task type: {exam_type}\n"
            f"Criterion: {criterion}\n"
            f"Criterion instructions: {CRITERION_PROMPTS[criterion]}\n\n"
            f"Essay:\n{essay_text}"
        )
        system = (
            SYSTEM_PROMPT
            + "\n\nCriterion-specific examiner instruction: "
            + CRITERION_PROMPTS[criterion]
        )
        return await self._execute(criterion, essay_text, prompt, system)

    async def evaluate_exam_task(
        self,
        criterion: Criterion,
        essay_text: str,
        exam_type: str,
        task_number: TaskNumber,
        chart_context: str | None = None,
        task_prompt: str | None = None,
    ) -> AgentExecution:
        task_instructions = _task_instructions(exam_type, task_number)

        prompt_sections = [
            f"IELTS exam/task type: {exam_type}",
            f"Task number: Task {task_number}",
            f"Criterion: {criterion}",
            f"Criterion instructions: {CRITERION_PROMPTS[criterion]}",
            f"Task-specific instructions: {task_instructions}",
        ]
        if task_prompt:
            prompt_sections.append(f"Exact task question given to the candidate: {task_prompt}")

        if chart_context:
            prompt_sections.append(
                "Chart/graph/table/diagram description (for verifying data accuracy "
                f"only, not part of the candidate's writing): {chart_context}"
            )
        prompt_sections.append(f"Essay:\n{essay_text}")
        prompt = "\n\n".join(prompt_sections)

        system = (
            SYSTEM_PROMPT
            + "\n\nCriterion-specific examiner instruction: "
            + CRITERION_PROMPTS[criterion]
            + "\n\nTask-specific examiner instruction: "
            + task_instructions
        )
        return await self._execute(criterion, essay_text, prompt, system)

    async def _execute(
        self,
        criterion: Criterion,
        essay_text: str,
        prompt: str,
        system: str,
    ) -> AgentExecution:
        started = time.perf_counter()
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1600,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - started) * 1000
        raw = RawAgentResponse.model_validate_json(_json_object(_response_text(response)))
        feedback = raw.feedback.rstrip() + "\n\nSentence-level examples:\n" + "\n".join(
            f"{index}. {example}"
            for index, example in enumerate(raw.sentence_examples, start=1)
        )
        result = CriterionEvaluation(
            criterion=criterion,
            band_score=_round_to_half(raw.band_score),
            feedback=feedback,
            highlighted_issues=_annotate_issues(essay_text, raw.highlighted_issues),
        )
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cost_usd = (prompt_tokens * 3 + completion_tokens * 15) / 1_000_000
        return AgentExecution(
            result=result,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )


@lru_cache
def get_agent_runner() -> WritingAgentRunner:
    from anthropic import AsyncAnthropic

    settings = get_settings()
    client = AsyncAnthropic(
        api_key=settings.anthropic_api_key or "not-configured",
        timeout=settings.anthropic_timeout_seconds,
    )
    return WritingAgentRunner(client, model=settings.writing_model)


async def _public_evaluation(
    criterion: Criterion,
    essay_text: str,
    exam_type: str,
    runner: WritingAgentRunner | None,
) -> dict[str, Any]:
    execution = await (runner or get_agent_runner()).evaluate(
        criterion, essay_text, exam_type
    )
    return execution.result.model_dump()


async def evaluate_task_response(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None
) -> dict[str, Any]:
    return await _public_evaluation("task_response", essay_text, exam_type, runner)


async def evaluate_cohesion(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None
) -> dict[str, Any]:
    return await _public_evaluation("cohesion", essay_text, exam_type, runner)


async def evaluate_vocabulary(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None
) -> dict[str, Any]:
    return await _public_evaluation("vocabulary", essay_text, exam_type, runner)


async def evaluate_grammar(
    essay_text: str, exam_type: str, runner: WritingAgentRunner | None = None
) -> dict[str, Any]:
    return await _public_evaluation("grammar", essay_text, exam_type, runner)

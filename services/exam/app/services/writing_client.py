import logging
import os
from typing import Literal
from uuid import UUID

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class WritingServiceError(Exception):
    """Raised when the Writing service fails or returns an unexpected response."""


class ExamTaskEvaluationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    userId: str = Field(min_length=1, max_length=128)
    essayText: str = Field(min_length=1, max_length=10000)
    examType: str = Field(min_length=1, max_length=64)
    examSessionId: str = Field(min_length=1, max_length=128)
    taskNumber: int = Field(ge=1, le=2)
    stimulusS3Key: str | None = None
    taskPrompt: str | None = Field(default=None, max_length=2000)


class InlineIssue(BaseModel):
    """
    One underlined span in the candidate's response.

    The field names here are the Writing service's own
    (services/writing/app/schemas.py InlineIssue). They used to be modelled as
    `issue`/`start`/`end`, which no Writing service response has ever contained:
    the model emits `issue_type`/`start_char`/`end_char`. AliasChoices keeps the
    older spelling accepted so any caller or fixture still sending it validates,
    while serialisation is canonical on the names the service actually uses.
    """

    model_config = ConfigDict(populate_by_name=True)

    text: str
    issue_type: str = Field(validation_alias=AliasChoices("issue_type", "issue"))
    suggestion: str
    start_char: int = Field(
        ge=0, validation_alias=AliasChoices("start_char", "start")
    )
    end_char: int = Field(ge=0, validation_alias=AliasChoices("end_char", "end"))


class CriterionEvaluation(BaseModel):
    """
    One criterion's mark.

    `inline_issues` previously had no default and was spelled
    `highlighted_issues`, so validating a genuine Writing service response
    raised ValidationError — which `evaluate_exam_essay` does not catch, so it
    surfaced as an unhandled 500 on every writing submit rather than as a
    WritingServiceError. Defaulting to an empty list additionally means a
    criterion that produced no underlines can never fail the whole submit.
    """

    model_config = ConfigDict(populate_by_name=True)

    criterion: Literal[
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    ]
    band_score: float = Field(ge=0.0, le=9.0)
    feedback: str
    # Present on the Writing service's payload; carried through so the exam
    # result can show it without a second call.
    improvement_tip: str | None = None
    word_count: int | None = None
    inline_issues: list[InlineIssue] = Field(
        default_factory=list,
        validation_alias=AliasChoices("inline_issues", "highlighted_issues"),
    )


class ExamTaskEvaluationResponse(BaseModel):
    essay_id: int
    exam_session_id: str
    task_number: int
    evaluations: list[CriterionEvaluation]
    overall_band: float = Field(ge=0.0, le=9.0)
    from_cache: bool


class WritingClient:
    """
    Thin async client around the Writing service's exam essay evaluation endpoint.
    """

    def __init__(
        self,
        base_url: str,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        # A single exam task runs four criterion agents against the LLM. Measured
        # against AgentRouter that takes ~50s end to end, so the previous 30s
        # default timed out every real evaluation and the call failed as
        # "Failed to reach Writing service after 2 attempt(s)" — an upstream
        # timeout wearing a connectivity error's costume.
        # Measured worst case against AgentRouter with claude-opus-4-8: ~200s for
        # one task (four criterion agents, extended thinking, one re-ask when an
        # agent answers unparseably). 300s leaves headroom without letting a
        # genuinely wedged call hang forever.
        self.timeout_s = (
            timeout_s
            if timeout_s is not None
            else float(os.getenv("WRITING_CLIENT_TIMEOUT_SECONDS", "300"))
        )
        # Retries are off by default. Retrying a timed-out evaluation does not
        # help: the first attempt is usually still running upstream, so a retry
        # doubles LLM cost and load while the caller waits twice as long for the
        # same outcome. Genuine connection errors fail fast and are surfaced.
        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(os.getenv("WRITING_CLIENT_MAX_RETRIES", "0"))
        )

    async def evaluate_exam_essay(
        self,
        user_id: str,
        essay_text: str,
        exam_type: str,
        exam_session_id: UUID,
        task_number: int,
        stimulus_s3_key: str | None = None,
        task_prompt: str | None = None,
    ) -> ExamTaskEvaluationResponse:
        """
        Calls POST /essays/evaluate/exam on the Writing service.

        Raises:
            WritingServiceError: on network failure, timeout, or a non-2xx response
                (including a 502 from the upstream service when evaluation itself fails).
        """
        request_payload = ExamTaskEvaluationRequest(
            userId=user_id,
            essayText=essay_text,
            examType=exam_type,
            examSessionId=str(exam_session_id),
            taskNumber=task_number,
            stimulusS3Key=stimulus_s3_key,
            taskPrompt=task_prompt,
        )

        url = f"{self.base_url}/essays/evaluate/exam"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    response = await client.post(
                        url,
                        json=request_payload.model_dump(),
                    )
                response.raise_for_status()
                try:
                    return ExamTaskEvaluationResponse.model_validate(
                        response.json()
                    )
                except ValidationError as exc:
                    # A 2xx whose body this client cannot read is an upstream
                    # contract problem, not a transient one, so it is not
                    # retried. It is raised as WritingServiceError so the caller
                    # turns it into a 502 (an upstream failure) instead of
                    # letting a raw ValidationError escape as an unhandled 500.
                    raise WritingServiceError(
                        f"Writing service returned an unreadable evaluation: {exc}"
                    ) from exc

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 502:
                    raise WritingServiceError(
                        f"Essay evaluation failed upstream: {exc.response.text}"
                    ) from exc
                last_error = exc
                logger.warning(
                    "Writing service returned %s on attempt %d/%d",
                    exc.response.status_code,
                    attempt + 1,
                    self.max_retries + 1,
                )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                logger.warning(
                    "Writing service network error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )

        raise WritingServiceError(
            f"Failed to reach Writing service after {self.max_retries + 1} attempt(s)"
        ) from last_error

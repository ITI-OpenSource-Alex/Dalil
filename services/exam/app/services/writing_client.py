import logging
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

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


class HighlightedIssue(BaseModel):
    text: str
    issue: str
    suggestion: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class CriterionEvaluation(BaseModel):
    criterion: Literal[
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    ]
    band_score: float = Field(ge=0.0, le=9.0)
    feedback: str
    highlighted_issues: list[HighlightedIssue]


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
        timeout_s: float = 30.0,
        max_retries: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_retries = max_retries

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
                return ExamTaskEvaluationResponse.model_validate(response.json())

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
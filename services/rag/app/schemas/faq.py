from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.faq_policy import classify_question


class FAQSource(BaseModel):
    source_url: str
    title: str | None = None


class FAQUpsertRequest(BaseModel):
    """GOA-045 admin payload for POST /internal/faq.

    `source_url` and the review window are required rather than optional
    because an entry without them cannot express when it stops being
    trustworthy -- and the whole hazard of a cached answer is that it stays
    plausible long after it stops being true.
    """

    question_pattern: str = Field(min_length=5, max_length=500)
    answer_markdown: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=100)
    sources: list[FAQSource] = Field(default_factory=list)
    # Defaults to a year, matching the seed migration. Shorten it for anything
    # that tracks a consular process.
    review_interval_days: int = Field(default=365, ge=1, le=3650)
    # Absent means "reviewed now", which is what adding or editing an entry is.
    reviewed_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def _source_url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("source_url must be an http(s) URL")
        return v

    @field_validator("question_pattern")
    @classmethod
    def _question_must_not_be_source_sensitive(cls, v: str) -> str:
        """Refuse to curate an answer that should never be cached.

        This is the same classifier the query path uses, applied at write time.
        Rejecting on the way in is worth doing even though the read path already
        bypasses these questions: without it the table accumulates entries that
        can never be served, which reads as coverage to anyone looking at a row
        count and hides the fact that the answer is coming from retrieval.
        """
        verdict = classify_question(v)
        if not verdict.allowed:
            raise ValueError(
                f"refusing to curate a source-sensitive question ({verdict.reason}): "
                "its answer depends on a figure an authority can change, so it must "
                "be served from live retrieval with a current citation"
            )
        return v


class FAQUpsertResponse(BaseModel):
    id: str
    question_pattern: str
    category: str | None
    source_url: str
    reviewed_at: datetime
    review_interval_days: int
    created: bool

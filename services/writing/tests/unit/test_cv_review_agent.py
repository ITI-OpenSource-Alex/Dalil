from types import SimpleNamespace

import pytest

from app.config import Settings
from app.schemas import CVReviewResponse, CVReviewSection
from app.services.cv_review import (
    CVReviewRunner,
    CVReviewSummary,
    cv_review_cache_key,
    cv_review_response,
)


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.payload)],
            usage=SimpleNamespace(input_tokens=120, output_tokens=80),
        )


class FakeClient:
    def __init__(self, payload):
        self.messages = FakeMessages(payload)


@pytest.mark.asyncio
async def test_structured_output_parses_to_cv_review_section_schema():
    client = FakeClient(
        """
        {"name":"Skills gaps","score":72,
         "issues":["Missing cloud deployment evidence"],
         "suggestions":["Add AWS services used and measurable outcomes."]}
        """
    )
    runner = CVReviewRunner(client)

    execution = await runner.review_section(
        "Skills gaps",
        cv_context="Python developer with PostgreSQL experience.",
        target_country="Germany",
        target_field="Computer Science",
        country_conventions="German CVs may include a photo by convention.",
    )

    assert execution.result == CVReviewSection(
        name="Skills gaps",
        score=72,
        issues=["Missing cloud deployment evidence"],
        suggestions=["Add AWS services used and measurable outcomes."],
    )
    assert client.messages.calls[0]["model"] == "claude-opus-5"


def test_cv_review_response_schema_matches_goa_025_contract():
    response = cv_review_response(
        CVReviewSummary(
            overall_score=88,
            sections=[
                CVReviewSection(
                    name="ATS keyword optimization",
                    score=88,
                    issues=[],
                    suggestions=["Add target-field keywords where accurate."],
                )
            ],
            total_tokens=0,
        )
    )

    payload = response.model_dump()
    assert CVReviewResponse.model_validate(payload)
    assert set(payload) == {"overallScore", "sections"}
    assert set(payload["sections"][0]) == {"name", "score", "issues", "suggestions"}


def test_cache_key_changes_only_when_cv_or_target_changes():
    settings = Settings(
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url=None,
        s3_bucket="bucket",
        cv_uploaded_queue_url="queue",
    )

    first = cv_review_cache_key("cv text", "Germany", "Computer Science", settings)
    same_target_case = cv_review_cache_key(
        "cv text", " germany ", "computer science", settings
    )
    different_field = cv_review_cache_key("cv text", "Germany", "Business", settings)

    assert first == same_target_case
    assert first != different_field

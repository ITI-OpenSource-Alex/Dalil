import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.schemas import CVReviewSection
from app.services import cv_review


class FakeMessages:
    def __init__(self, response_text):
        self.response_text = response_text
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text=self.response_text)],
            usage=SimpleNamespace(input_tokens=40, output_tokens=20),
        )


class FakeClient:
    def __init__(self, response_text):
        self.messages = FakeMessages(response_text)


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.setex_calls = []

    async def get(self, key):
        return self.storage.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.storage[key] = value


@pytest.mark.asyncio
async def test_generate_review_parses_structured_json():
    fake_client = FakeClient(
        json.dumps(
            {
                "name": "Country-specific conventions",
                "score": 88,
                "issues": ["Photo missing for Germany"],
                "suggestions": ["Add a professional photo for German applications."],
            }
        )
    )
    runner = cv_review.CVReviewRunner(fake_client)

    result = await runner.review_section(
        "Country-specific conventions",
        cv_context="Jane Doe CV text.",
        target_country="Germany",
        target_field="Software Engineering",
        country_conventions="German CVs may include a photo.",
    )

    assert result.result == CVReviewSection(
        name="Country-specific conventions",
        score=88,
        issues=["Photo missing for Germany"],
        suggestions=["Add a professional photo for German applications."],
    )
    assert fake_client.messages.calls[0]["model"] == "claude-opus-5"


@pytest.mark.asyncio
async def test_review_cv_uses_cache_on_repeat(monkeypatch):
    fake_redis = FakeRedis()
    calls = []
    settings = Settings(
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url=None,
        s3_bucket="bucket",
        cv_uploaded_queue_url="queue",
    )

    class FakeCoordinator:
        async def review(self, **kwargs):
            calls.append(kwargs)
            sections = [
                CVReviewSection(
                    name="Structure and formatting",
                    score=74,
                    issues=["Needs a clearer summary"],
                    suggestions=["Move the profile summary to the top."],
                )
            ]
            if kwargs.get("on_partial"):
                await kwargs["on_partial"](sections[0])
            return cv_review.CVReviewSummary(
                overall_score=74,
                sections=sections,
                total_tokens=100,
            )

        async def replay_cached(self, payload, *, on_partial=None):
            response = cv_review.CVReviewResponse.model_validate(payload)
            for section in response.sections:
                if on_partial:
                    await on_partial(section)
            return cv_review.CVReviewSummary(
                overall_score=response.overallScore,
                sections=response.sections,
                total_tokens=0,
            )

    cache_key = cv_review.cv_review_cache_key(
        "Jane Doe CV text.",
        "Germany",
        "Software Engineering",
        settings,
    )

    first = await FakeCoordinator().review(
        extracted_text="Jane Doe CV text.",
        structured_data={"skills": ["Python"]},
        target_country="Germany",
        target_field="Software Engineering",
        country_conventions="German CVs may include a photo.",
    )
    await cv_review.set_cached_review(
        fake_redis,
        cache_key,
        cv_review.cv_review_response(first).model_dump(mode="json"),
    )
    cached_payload = await cv_review.get_cached_review(fake_redis, cache_key)
    second = await FakeCoordinator().replay_cached(cached_payload)

    assert len(calls) == 1
    assert first.overall_score == second.overall_score == 74
    assert first.sections == second.sections
    assert fake_redis.setex_calls[0][1] == 24 * 60 * 60

import json
from types import SimpleNamespace

import pytest

from app.config import Settings
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

    async def get(self, key):
        return self.storage.get(key)

    async def setex(self, key, ttl, value):
        self.storage[key] = value


@pytest.mark.asyncio
async def test_generate_review_parses_structured_json(monkeypatch):
    body = {
        "overallScore": 86,
        "sections": [
            {
                "name": "Structure/Formatting",
                "score": 80,
                "issues": ["No contact header"],
                "suggestions": ["Add a clear contact header at the top."],
            },
            {
                "name": "Skills Gaps",
                "score": 78,
                "issues": ["Missing cloud skills"],
                "suggestions": ["Add AWS, Docker, and CI/CD experience."],
            },
            {
                "name": "ATS Keywords",
                "score": 84,
                "issues": ["Missing role keywords"],
                "suggestions": ["Use keywords from the target job description."],
            },
            {
                "name": "Length Appropriateness",
                "score": 90,
                "issues": [],
                "suggestions": ["Keep it to one page for early-career roles."],
            },
            {
                "name": "Country Conventions",
                "score": 88,
                "issues": ["Photo missing for Germany"],
                "suggestions": ["Add a professional photo for German applications."],
            },
        ],
    }
    fake_client = FakeClient(json.dumps(body))
    monkeypatch.setattr(cv_review, "_build_client", lambda _settings: fake_client)

    settings = Settings(
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_endpoint_url=None,
        s3_bucket="bucket",
        cv_uploaded_queue_url="queue",
    )

    result = await cv_review._generate_review(
        "Jane Doe CV text.",
        {"skills": ["Python"]},
        "Germany",
        "Software Engineering",
        conventions={"photo_required": True},
        settings=settings,
    )

    assert result.overallScore == 86
    assert [section.name for section in result.sections] == [
        "Structure/Formatting",
        "Skills Gaps",
        "ATS Keywords",
        "Length Appropriateness",
        "Country Conventions",
    ]
    assert fake_client.messages.calls[0]["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_review_cv_uses_cache_on_repeat(monkeypatch):
    fake_redis = FakeRedis()
    calls = []

    async def fake_generate_review(*args, **kwargs):
        calls.append((args, kwargs))
        return cv_review.CVReviewOutput.model_validate(
            {
                "overallScore": 74,
                "sections": [
                    {
                        "name": "Structure/Formatting",
                        "score": 72,
                        "issues": ["Needs a clearer summary"],
                        "suggestions": ["Move the profile summary to the top."],
                    },
                    {
                        "name": "Skills Gaps",
                        "score": 68,
                        "issues": ["No skills section"],
                        "suggestions": ["Add a dedicated skills section."],
                    },
                    {
                        "name": "ATS Keywords",
                        "score": 70,
                        "issues": ["Few field keywords"],
                        "suggestions": ["Mirror keywords from the target job description."],
                    },
                    {
                        "name": "Length Appropriateness",
                        "score": 80,
                        "issues": [],
                        "suggestions": ["Keep the CV concise."],
                    },
                    {
                        "name": "Country Conventions",
                        "score": 76,
                        "issues": ["Photo omission for Germany"],
                        "suggestions": ["Include a photo for German applications if appropriate."],
                    },
                ],
            }
        )

    async def fake_conventions(*_args, **_kwargs):
        return {"photo_required": True}

    monkeypatch.setattr(cv_review, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(cv_review, "_generate_review", fake_generate_review)
    monkeypatch.setattr(cv_review, "_fetch_country_conventions", fake_conventions)

    first = await cv_review.review_cv(
        "Jane Doe CV text.",
        {"skills": ["Python"]},
        "Germany",
        "Software Engineering",
    )
    second = await cv_review.review_cv(
        "Jane Doe CV text.",
        {"skills": ["Python"]},
        "Germany",
        "Software Engineering",
    )

    assert first.from_cache is False
    assert second.from_cache is True
    assert len(calls) == 1
    assert first.review.model_dump() == second.review.model_dump()

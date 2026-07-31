"""POST /cv/review — the CV review agent SSE endpoint."""

import json

import pytest

from app.models import CVReview
from app.services import cv_review as cv_review_service


def _make_cv(db_session, **overrides):
    defaults = dict(
        user_id="user-1",
        s3_key=f"cvs/{overrides.get('s3_key_suffix', 'a')}.pdf",
        original_filename="cv.pdf",
        status="ready",
        extracted_text="Ahmed Karim. BSc Computer Science, Cairo University.",
        structured_data={"name": "Ahmed Karim", "degree": "BSc Computer Science"},
    )
    overrides.pop("s3_key_suffix", None)
    defaults.update(overrides)
    cv = CVReview(**defaults)
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


class FakeRedis:
    def __init__(self):
        self.storage = {}

    async def get(self, key):
        return self.storage.get(key)

    async def setex(self, key, ttl, value):
        self.storage[key] = value


def _events(response_text):
    parsed = []
    for block in response_text.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        parsed.append((name, data))
    return parsed


def _review_payload(target_country="Germany", target_field="Software Engineering"):
    return {
        "userId": "user-1",
        "cvS3Key": "cvs/a.pdf",
        "targetCountry": target_country,
        "targetField": target_field,
    }


def test_unknown_cv_returns_404(client):
    response = client.post("/cv/review", json=_review_payload())
    assert response.status_code == 404


def test_another_users_cv_returns_403(client, db_session):
    cv = _make_cv(db_session, user_id="owner", s3_key_suffix="owned")

    response = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert response.status_code == 403
    assert "another user" in response.json()["detail"]


def test_unprocessed_cv_returns_409(client, db_session):
    cv = _make_cv(
        db_session,
        status="processing",
        extracted_text=None,
        structured_data=None,
        s3_key_suffix="pending",
    )

    response = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


def test_failed_extraction_surfaces_its_own_error(client, db_session):
    cv = _make_cv(
        db_session,
        status="failed",
        extracted_text=None,
        structured_data=None,
        error_message="Unsupported PDF encoding",
        s3_key_suffix="failed",
    )

    response = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert response.status_code == 409
    assert "Unsupported PDF encoding" in response.json()["detail"]


def test_ready_but_empty_cv_is_refused(client, db_session):
    cv = _make_cv(
        db_session,
        status="ready",
        extracted_text=None,
        structured_data=None,
        s3_key_suffix="empty",
    )

    response = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert response.status_code == 409
    assert "no extracted content" in response.json()["detail"]


def test_review_streams_sections_and_uses_cache(client, db_session, monkeypatch):
    cv = _make_cv(
        db_session,
        s3_key_suffix="ok",
        structured_data={"name": "Ahmed Karim", "degree": "BSc Computer Science"},
    )
    fake_redis = FakeRedis()
    calls = []

    async def fake_conventions(*_args, **_kwargs):
        return {"photo_required": True, "country": "Germany"}

    async def fake_generate_review(extracted_text, structured_data, target_country, target_field, **kwargs):
        calls.append((extracted_text, structured_data, target_country, target_field, kwargs["conventions"]))
        has_skills = bool((structured_data or {}).get("skills"))
        skills_issues = [] if has_skills else ["No dedicated skills section"]
        skills_suggestions = [] if has_skills else ["Add a concise skills section for ATS matching"]
        return cv_review_service.CVReviewOutput.model_validate(
            {
                "overallScore": 82,
                "sections": [
                    {
                        "name": "Structure/Formatting",
                        "score": 80,
                        "issues": ["Weak headline"],
                        "suggestions": ["Use a clearer professional headline."],
                    },
                    {
                        "name": "Skills Gaps",
                        "score": 70,
                        "issues": skills_issues,
                        "suggestions": skills_suggestions,
                    },
                    {
                        "name": "ATS Keywords",
                        "score": 84,
                        "issues": ["Missing cloud keywords"],
                        "suggestions": ["Include tools from the target job description."],
                    },
                    {
                        "name": "Length Appropriateness",
                        "score": 88,
                        "issues": [],
                        "suggestions": ["Keep the CV at one page for early-career roles."],
                    },
                    {
                        "name": "Country Conventions",
                        "score": 76,
                        "issues": ["Germany typically expects a photo"],
                        "suggestions": ["Consider adding a professional photo for German applications."],
                    },
                ],
            }
        )

    monkeypatch.setattr(cv_review_service, "_get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(cv_review_service, "_fetch_country_conventions", fake_conventions)
    monkeypatch.setattr(cv_review_service, "_generate_review", fake_generate_review)

    response = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    section_events = [data for name, data in events if name == "section"]
    complete_event = next(data for name, data in events if name == "complete")

    assert len(section_events) == 5
    assert {section["name"] for section in section_events} == {
        "Structure/Formatting",
        "Skills Gaps",
        "ATS Keywords",
        "Length Appropriateness",
        "Country Conventions",
    }
    assert any(
        "skills" in issue.lower()
        for section in section_events
        for issue in section["issues"]
    )
    assert complete_event["overallScore"] == 82
    assert len(calls) == 1

    second = client.post(
        "/cv/review",
        json={**_review_payload(), "cvS3Key": cv.s3_key},
    )

    assert second.status_code == 200
    assert len(calls) == 1
    second_events = _events(second.text)
    assert next(data for name, data in second_events if name == "complete")["overallScore"] == 82

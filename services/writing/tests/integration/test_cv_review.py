import json

import pytest

from app.models import CVReview
from app.schemas import CVReviewResponse, CVReviewSection


def _make_cv(db_session, **overrides):
    defaults = dict(
        user_id="user-1",
        s3_key=f"cvs/user-1/{overrides.get('s3_key_suffix', 'a')}.pdf",
        original_filename="cv.pdf",
        status="ready",
        extracted_text=(
            "Ahmed Karim\nBSc Computer Science, Cairo University\n"
            "Backend developer using Python, FastAPI, PostgreSQL, AWS."
        ),
        structured_data={
            "name": "Ahmed Karim",
            "degree": "BSc Computer Science",
            "skills": ["Python", "FastAPI", "PostgreSQL", "AWS"],
        },
    )
    overrides.pop("s3_key_suffix", None)
    defaults.update(overrides)
    cv = CVReview(**defaults)
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


def _payload(cv, **overrides):
    payload = {
        "userId": cv.user_id,
        "cvS3Key": cv.s3_key,
        "targetCountry": "Germany",
        "targetField": "Computer Science",
    }
    payload.update(overrides)
    return payload


def _sse_events(response):
    events = []
    for block in response.text.strip().split("\n\n"):
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            if line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if name:
            events.append((name, data))
    return events


class FakeCache:
    def __init__(self):
        self.values = {}
        self.setex_calls = []

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value
        return True


class FakeCoordinator:
    def __init__(self):
        self.review_calls = []
        self.replay_calls = []

    async def review(
        self,
        *,
        extracted_text,
        structured_data,
        target_country,
        target_field,
        country_conventions,
        program_context=None,
        on_partial=None,
    ):
        self.review_calls.append(
            {
                "extracted_text": extracted_text,
                "structured_data": structured_data,
                "target_country": target_country,
                "target_field": target_field,
                "country_conventions": country_conventions,
                "program_context": program_context,
            }
        )
        skills_issues = (
            ["No skills section is present in the extracted CV"]
            if not (structured_data or {}).get("skills")
            else ["No German language or research-methods keywords"]
        )
        sections = [
            CVReviewSection(
                name="Structure and formatting",
                score=82,
                issues=["No profile headline"],
                suggestions=["Add a concise academic profile headline."],
            ),
            CVReviewSection(
                name="Skills gaps",
                score=76,
                issues=skills_issues,
                suggestions=["Add relevant tools, methods, and language level."],
            ),
            CVReviewSection(
                name="ATS keyword optimization",
                score=79,
                issues=["Few target-field keywords"],
                suggestions=["Mirror target programme keywords where truthful."],
            ),
            CVReviewSection(
                name="Length appropriateness",
                score=90,
                issues=[],
                suggestions=["Keep the CV to one or two pages."],
            ),
            CVReviewSection(
                name="Country-specific conventions",
                score=83,
                issues=[],
                suggestions=["Use the expected German CV layout."],
            ),
        ]
        for section in sections:
            if on_partial:
                await on_partial(section)

        from app.services.cv_review import CVReviewSummary

        return CVReviewSummary(overall_score=82, sections=sections, total_tokens=500)

    async def replay_cached(self, payload, *, on_partial=None):
        self.replay_calls.append(payload)
        response = CVReviewResponse.model_validate(payload)
        for section in response.sections:
            if on_partial:
                await on_partial(section)

        from app.services.cv_review import CVReviewSummary

        return CVReviewSummary(
            overall_score=response.overallScore,
            sections=response.sections,
            total_tokens=0,
        )


@pytest.fixture
def cv_review_stubs(monkeypatch):
    cache = FakeCache()
    coordinator = FakeCoordinator()
    rag_calls = []

    async def fake_conventions(user_id, target_country, settings):
        rag_calls.append((user_id, target_country, settings.rag_service_url))
        return "German CV conventions: photo may be expected locally; keep concise."

    async def fake_programme(program_id, settings):
        assert settings.rag_service_url == "http://rag:8084"
        return {
            "id": program_id,
            "name": "MSc Data Engineering",
            "country": "Germany",
            "discipline": "computer_science",
            "min_ielts": 7.0,
        }

    monkeypatch.setattr("app.routers.cvs.get_redis_client", lambda settings: cache)
    monkeypatch.setattr(
        "app.routers.cvs.fetch_country_conventions", fake_conventions
    )
    monkeypatch.setattr(
        "app.routers.cvs._fetch_programme_requirements", fake_programme
    )

    from app.main import app
    from app.services.cv_review import get_cv_review_coordinator

    app.dependency_overrides[get_cv_review_coordinator] = lambda: coordinator
    yield cache, coordinator, rag_calls
    app.dependency_overrides.pop(get_cv_review_coordinator, None)


def test_unknown_cv_returns_404(client):
    response = client.post(
        "/cv/review",
        json={
            "userId": "user-1",
            "cvS3Key": "missing.pdf",
            "targetCountry": "Germany",
            "targetField": "Computer Science",
        },
    )
    assert response.status_code == 404


def test_unprocessed_cv_returns_409(client, db_session):
    cv = _make_cv(
        db_session,
        status="processing",
        extracted_text=None,
        structured_data=None,
        s3_key_suffix="pending",
    )

    response = client.post("/cv/review", json=_payload(cv))

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

    response = client.post("/cv/review", json=_payload(cv))

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

    response = client.post("/cv/review", json=_payload(cv))

    assert response.status_code == 409
    assert "no extracted content" in response.json()["detail"]


def test_cv_review_streams_structured_sections_and_complete_event(
    client, db_session, cv_review_stubs
):
    cache, coordinator, rag_calls = cv_review_stubs
    cv = _make_cv(db_session, s3_key_suffix="ok")

    response = client.post("/cv/review", json=_payload(cv))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response)
    section_events = [data for name, data in events if name == "section"]
    assert len(section_events) == 5
    assert events[-1][0] == "complete"

    complete = events[-1][1]
    CVReviewResponse.model_validate(complete)
    assert complete["overallScore"] == 82
    assert len(complete["sections"]) == 5
    assert complete["fromCache"] is False
    assert coordinator.review_calls[0]["structured_data"]["skills"] == [
        "Python",
        "FastAPI",
        "PostgreSQL",
        "AWS",
    ]
    assert "German CV conventions" in coordinator.review_calls[0]["country_conventions"]
    assert rag_calls == [("user-1", "Germany", "http://rag:8084")]
    assert len(cache.setex_calls) == 1
    assert cache.setex_calls[0][1] == 24 * 60 * 60


def test_missing_skills_section_returns_skills_gap_feedback(
    client, db_session, cv_review_stubs
):
    cv = _make_cv(
        db_session,
        s3_key_suffix="no-skills",
        extracted_text="Ahmed Karim\nBSc Computer Science, Cairo University.",
        structured_data={"name": "Ahmed Karim", "degree": "BSc Computer Science"},
    )

    response = client.post("/cv/review", json=_payload(cv))

    assert response.status_code == 200
    sections = [
        data
        for name, data in _sse_events(response)
        if name == "section" and data["name"] == "Skills gaps"
    ]
    assert sections
    assert "no skills section" in " ".join(sections[0]["issues"]).lower()


def test_programme_scoped_review_resolves_target_from_rag(
    client, db_session, cv_review_stubs
):
    _, coordinator, rag_calls = cv_review_stubs
    cv = _make_cv(db_session, s3_key_suffix="programme")

    response = client.post(
        "/cv/review",
        json={
            "userId": cv.user_id,
            "cvS3Key": cv.s3_key,
            "programId": "program-1",
        },
    )

    assert response.status_code == 200
    call = coordinator.review_calls[0]
    assert call["target_country"] == "Germany"
    assert call["target_field"] == "MSc Data Engineering"
    assert call["program_context"]["min_ielts"] == 7.0
    assert rag_calls == []


def test_redis_cache_hit_replays_without_llm_call(client, db_session, cv_review_stubs):
    cache, coordinator, _ = cv_review_stubs
    cv = _make_cv(db_session, s3_key_suffix="cache")

    first = client.post("/cv/review", json=_payload(cv))
    second = client.post("/cv/review", json=_payload(cv))

    assert first.status_code == second.status_code == 200
    first_complete = _sse_events(first)[-1][1]
    second_complete = _sse_events(second)[-1][1]
    assert first_complete["overallScore"] == second_complete["overallScore"] == 82
    assert first_complete["fromCache"] is False
    assert second_complete["fromCache"] is True
    assert len(coordinator.review_calls) == 1
    assert len(coordinator.replay_calls) == 1
    assert len(cache.values) == 1

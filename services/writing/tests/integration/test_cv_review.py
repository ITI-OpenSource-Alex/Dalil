"""POST /cv/review — the endpoint that did not exist (BUG-019).

The CV pipeline ended at extraction. Since BUG-018 was fixed it reliably
produces good structured data and nothing consumed it; Orchestration's
CV_REVIEW intent had no endpoint to call and the route 404'd on both the
writing service and the gateway.

The model call itself is stubbed here. It is a single ~2000-token generation
against a provider measured between 2.5s and 110s (BUG-038), so exercising it
for real would make this suite slow and flaky for no extra signal — the
guard rails below are what a test can pin. A real end-to-end review was
verified separately against the running stack.
"""

import pytest

from app.models import CVReview


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


def test_unknown_cv_returns_404(client):
    response = client.post("/cv/review", json={"userId": "user-1", "cvId": 999999})
    assert response.status_code == 404


def test_another_users_cv_returns_403(client, db_session):
    cv = _make_cv(db_session, user_id="owner", s3_key_suffix="owned")

    response = client.post("/cv/review", json={"userId": "intruder", "cvId": cv.id})

    assert response.status_code == 403
    assert "another user" in response.json()["detail"]


def test_ownership_is_checked_before_readiness(client, db_session):
    """A caller must not learn anything about someone else's CV.

    If readiness were checked first, a 409 would confirm the CV exists and is
    still processing while a 403 would mean it is ready -- leaking state about
    another user's document through the status code alone.
    """
    cv = _make_cv(
        db_session, user_id="owner", status="processing",
        extracted_text=None, structured_data=None, s3_key_suffix="processing",
    )

    response = client.post("/cv/review", json={"userId": "intruder", "cvId": cv.id})

    assert response.status_code == 403


def test_unprocessed_cv_returns_409(client, db_session):
    cv = _make_cv(
        db_session, status="processing", extracted_text=None,
        structured_data=None, s3_key_suffix="pending",
    )

    response = client.post("/cv/review", json={"userId": "user-1", "cvId": cv.id})

    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


def test_failed_extraction_surfaces_its_own_error(client, db_session):
    """Reviewing a failed extraction would invent feedback about nothing.

    The CV has no text, so the model would confidently describe a document it
    never saw -- the same class of failure as reporting success over an empty
    result in BUG-010a and BUG-022.
    """
    cv = _make_cv(
        db_session, status="failed", extracted_text=None, structured_data=None,
        error_message="Unsupported PDF encoding", s3_key_suffix="failed",
    )

    response = client.post("/cv/review", json={"userId": "user-1", "cvId": cv.id})

    assert response.status_code == 409
    assert "Unsupported PDF encoding" in response.json()["detail"]


def test_ready_but_empty_cv_is_refused(client, db_session):
    cv = _make_cv(
        db_session, status="ready", extracted_text=None,
        structured_data=None, s3_key_suffix="empty",
    )

    response = client.post("/cv/review", json={"userId": "user-1", "cvId": cv.id})

    assert response.status_code == 409
    assert "no extracted content" in response.json()["detail"]


def test_successful_review_returns_the_model_output(client, db_session, monkeypatch):
    cv = _make_cv(db_session, s3_key_suffix="ok")

    async def fake_review(extracted_text, structured_data):
        assert "Ahmed Karim" in (extracted_text or "")
        return {
            "summary": "Solid backend profile, thin on academic detail.",
            "sections": [
                {
                    "section": "Education",
                    "strengths": ["BSc clearly stated"],
                    "gaps": ["No graduation year"],
                    "suggestions": ["State your graduation year and thesis topic"],
                }
            ],
            "readiness": "adequate",
            "missing_for_study_abroad": ["Graduation year"],
        }

    monkeypatch.setattr("app.routers.cvs.review_cv", fake_review)

    response = client.post("/cv/review", json={"userId": "user-1", "cvId": cv.id})

    assert response.status_code == 200
    body = response.json()
    assert body["cvId"] == cv.id
    assert body["readiness"] == "adequate"
    assert body["sections"][0]["section"] == "Education"


def test_model_failure_becomes_502_not_500(client, db_session, monkeypatch):
    """A provider timeout is an upstream problem, not a bug in this service."""
    cv = _make_cv(db_session, s3_key_suffix="boom")

    async def boom(extracted_text, structured_data):
        raise TimeoutError("provider did not respond")

    monkeypatch.setattr("app.routers.cvs.review_cv", boom)

    response = client.post("/cv/review", json={"userId": "user-1", "cvId": cv.id})

    assert response.status_code == 502

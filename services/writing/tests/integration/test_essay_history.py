from app.models import Essay


def _make_essay(db_session, **overrides):
    defaults = dict(
        user_id="writer-123",
        extracted_text="A" * 200,
        submission_type="practice",
        exam_type=None,
        task_number=None,
        status="ready",
        evaluation_result=None,
    )
    defaults.update(overrides)
    essay = Essay(**defaults)
    db_session.add(essay)
    db_session.commit()
    db_session.refresh(essay)
    return essay


def test_list_essays_returns_only_the_requested_user(client, db_session):
    _make_essay(db_session, user_id="writer-123")
    _make_essay(db_session, user_id="someone-else")

    response = client.get("/essays", params={"user_id": "writer-123"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["submission_type"] == "practice"


def test_list_essays_orders_most_recent_first(client, db_session):
    older = _make_essay(db_session, user_id="writer-123", extracted_text="older essay")
    newer = _make_essay(db_session, user_id="writer-123", extracted_text="newer essay")

    response = client.get("/essays", params={"user_id": "writer-123"})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [newer.id, older.id]


def test_list_essays_extracts_overall_band_from_evaluation_result(client, db_session):
    _make_essay(
        db_session,
        user_id="writer-123",
        evaluation_result={"evaluations": [], "overall_band": 6.5},
    )

    response = client.get("/essays", params={"user_id": "writer-123"})

    assert response.status_code == 200
    assert response.json()[0]["overall_band"] == 6.5


def test_list_essays_overall_band_is_null_when_not_yet_evaluated(client, db_session):
    _make_essay(db_session, user_id="writer-123", evaluation_result=None)

    response = client.get("/essays", params={"user_id": "writer-123"})

    assert response.status_code == 200
    assert response.json()[0]["overall_band"] is None


def test_list_essays_filters_by_submission_type(client, db_session):
    _make_essay(db_session, user_id="writer-123", submission_type="practice")
    _make_essay(db_session, user_id="writer-123", submission_type="exam")

    response = client.get(
        "/essays", params={"user_id": "writer-123", "submission_type": "exam"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["submission_type"] == "exam"


def test_list_essays_excerpt_is_truncated(client, db_session):
    _make_essay(db_session, user_id="writer-123", extracted_text="x" * 500)

    response = client.get("/essays", params={"user_id": "writer-123"})

    excerpt = response.json()[0]["excerpt"]
    assert len(excerpt) == 141  # 140 chars + the ellipsis marker
    assert excerpt.endswith("…")


def test_list_essays_paginates_at_twenty_per_page(client, db_session):
    for i in range(25):
        _make_essay(db_session, user_id="writer-123", extracted_text=f"essay {i}")

    first_page = client.get("/essays", params={"user_id": "writer-123"})
    second_page = client.get("/essays", params={"user_id": "writer-123", "page": 2})

    assert len(first_page.json()) == 20
    assert len(second_page.json()) == 5
    first_ids = {item["id"] for item in first_page.json()}
    second_ids = {item["id"] for item in second_page.json()}
    assert first_ids.isdisjoint(second_ids)


def test_list_essays_missing_user_id_is_422(client):
    response = client.get("/essays")
    assert response.status_code == 422


def test_list_essays_unknown_user_returns_empty_list(client, db_session):
    _make_essay(db_session, user_id="writer-123")

    response = client.get("/essays", params={"user_id": "nobody-here"})

    assert response.status_code == 200
    assert response.json() == []

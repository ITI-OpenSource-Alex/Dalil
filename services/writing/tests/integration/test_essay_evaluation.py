import json

from app.models import Essay


PAYLOAD = {
    "userId": "writer-123",
    "essayText": "Public transport should be improved because it benefits every resident.",
    "submissionType": "computer_based",
    "examType": "academic_task_2",
}


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


def test_submit_text_returns_four_evaluations_and_persists_jsonb(
    evaluation_client, db_session
):
    client, runner, _langfuse, _trace = evaluation_client

    response = client.post("/essays/evaluate", json=PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert len(body["evaluations"]) == 4
    assert {item["criterion"] for item in body["evaluations"]} == {
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    }
    assert body["overall_band"] == 6.5
    assert body["from_cache"] is False
    essay = db_session.get(Essay, body["essay_id"])
    assert essay.status == "evaluated"
    assert len(essay.evaluation_result["evaluations"]) == 4
    assert essay.evaluation_result["overall_band"] == 6.5
    assert len(runner.calls) == 4


def test_evaluation_trace_has_one_root_and_exactly_four_child_spans(evaluation_client):
    client, _runner, langfuse, trace = evaluation_client

    response = client.post("/essays/evaluate", json=PAYLOAD)

    assert response.status_code == 200
    langfuse.trace.assert_called_once()
    trace_call = langfuse.trace.call_args.kwargs
    assert trace_call["user_id"] == PAYLOAD["userId"]
    assert trace_call["metadata"]["essay_id"] == response.json()["essay_id"]
    assert trace_call["metadata"]["task_type"] == PAYLOAD["examType"]
    assert trace.span.call_count == 4
    span_criteria = {
        call.kwargs["input"]["criterion"] for call in trace.span.call_args_list
    }
    assert span_criteria == {
        "task_response",
        "cohesion",
        "vocabulary",
        "grammar",
    }


def test_streaming_endpoint_yields_each_agent_then_complete(
    evaluation_client, db_session
):
    client, _runner, _langfuse, _trace = evaluation_client
    essay = Essay(
        user_id=PAYLOAD["userId"],
        extracted_text=PAYLOAD["essayText"],
        submission_type=PAYLOAD["submissionType"],
        exam_type=PAYLOAD["examType"],
        status="ready",
    )
    db_session.add(essay)
    db_session.commit()
    db_session.refresh(essay)

    response = client.post(f"/essays/{essay.id}/evaluate")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    criterion_events = [data for name, data in events if name == "criterion"]
    assert len(criterion_events) == 4
    assert len({item["criterion"] for item in criterion_events}) == 4
    assert events[-1][0] == "complete"
    assert events[-1][1]["overall_band"] == 6.5
    assert db_session.get(Essay, essay.id).evaluation_result is not None


def test_second_identical_submission_uses_cache_and_increases_hit_rate(
    evaluation_client,
):
    client, runner, _langfuse, _trace = evaluation_client

    first = client.post("/essays/evaluate", json=PAYLOAD)
    metrics_after_first = client.get("/metrics").text
    second = client.post("/essays/evaluate", json=PAYLOAD)
    metrics_after_second = client.get("/metrics").text

    assert first.status_code == second.status_code == 200
    assert first.json()["from_cache"] is False
    assert second.json()["from_cache"] is True
    assert len(runner.calls) == 4
    assert "goa_writing_cache_hit_rate 0.0" in metrics_after_first
    assert "goa_writing_cache_hit_rate 0.5" in metrics_after_second
    assert "goa_writing_evaluation_latency_ms_bucket" in metrics_after_second
    assert "goa_writing_agent_band_score_bucket" in metrics_after_second


def test_streaming_unknown_essay_returns_404(evaluation_client):
    client, *_ = evaluation_client
    response = client.post("/essays/99999/evaluate")
    assert response.status_code == 404


def test_create_essay_returns_201_with_id_and_ready_status(evaluation_client, db_session):
    client, *_ = evaluation_client
    payload = {
        "userId": "writer-123",
        "essayText": "This is a newly created essay.",
        "submissionType": "task2",
    }
    response = client.post("/essays", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["status"] == "ready"
    
    essay = db_session.get(Essay, body["id"])
    assert essay is not None
    assert essay.extracted_text == payload["essayText"]
    assert essay.status == "ready"


def test_create_essay_missing_essay_text_422(evaluation_client):
    client, *_ = evaluation_client
    response = client.post("/essays", json={"userId": "writer-123", "submissionType": "task1"})
    assert response.status_code == 422


def test_create_then_stream_evaluate(evaluation_client, db_session):
    client, _runner, _langfuse, _trace = evaluation_client
    payload = {
        "userId": "writer-123",
        "essayText": "Public transport should be improved.",
        "submissionType": "task2",
    }
    create_response = client.post("/essays", json=payload)
    assert create_response.status_code == 201
    essay_id = create_response.json()["id"]

    eval_response = client.post(f"/essays/{essay_id}/evaluate")
    assert eval_response.status_code == 200
    events = _events(eval_response.text)
    assert events[-1][0] == "complete"


def test_create_with_exam_session_id_persists(evaluation_client, db_session):
    client, *_ = evaluation_client
    payload = {
        "userId": "writer-123",
        "essayText": "Exam text.",
        "submissionType": "task1",
        "examSessionId": "session-xyz",
    }
    response = client.post("/essays", json=payload)
    assert response.status_code == 201
    body = response.json()
    
    essay = db_session.get(Essay, body["id"])
    assert essay.exam_session_id == "session-xyz"

"""Integration tests for the Writing evaluation engine (WR-01 .. WR-06).

These tests exercise the app via the existing test fixtures in
services/writing/tests/conftest.py and assert SSE streaming, caching,
validation, and Langfuse trace generation.
"""

import json
import time
from statistics import mean

import pytest

from app.evaluation import calculate_overall_band


@pytest.mark.asyncio
async def test_wr01_create_essay_returns_201_and_ready(evaluation_client, db_session):
    client, _runner, _langfuse, _trace = evaluation_client

    long_text = (
        "This is a sample Task 2 essay. " * 60
    )  # ~240 words when split by spaces — sufficient for Task 2 sizing

    resp = client.post(
        "/essays",
        json={
            "userId": "wr-user-01",
            "essayText": long_text,
            "submissionType": "task2",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["status"] == "ready"


def _parse_sse(text: str):
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            if line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        events.append((name, data))
    return events


@pytest.mark.asyncio
async def test_wr02_stream_and_wr03_final_result_has_rounded_band(evaluation_client, db_session):
    client, _runner, _langfuse, _trace = evaluation_client

    create = client.post(
        "/essays",
        json={
            "userId": "wr-user-02",
            "essayText": "Technology benefits society by improving access to information and education.",
            "submissionType": "task2",
        },
    )
    assert create.status_code == 201
    essay_id = create.json()["id"]

    resp = client.post(f"/essays/{essay_id}/evaluate")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    criterion_events = [data for name, data in events if name == "criterion"]
    complete_events = [data for name, data in events if name == "complete"]

    # Assert partial results arrived (per-criterion) and not just a single final chunk
    assert len(criterion_events) == 4

    # Final result present and includes band rounding check
    assert len(complete_events) == 1
    final = complete_events[0]
    assert "overall_band" in final
    bands = [item["band_score"] for item in final["evaluations"]]
    expected = calculate_overall_band(bands)
    assert final["overall_band"] == expected

    # Ensure highlighted/inline issues exist and have char spans
    for ev in final["evaluations"]:
        assert "inline_issues" in ev
        assert len(ev["inline_issues"]) > 0
        issue = ev["inline_issues"][0]
        assert isinstance(issue.get("start_char"), int)
        assert isinstance(issue.get("end_char"), int)


@pytest.mark.asyncio
async def test_wr04_oversized_essay_rejected_with_422(evaluation_client):
    client, _runner, _langfuse, _trace = evaluation_client

    oversized = "a" * 5001
    resp = client.post(
        "/essays",
        json={
            "userId": "wr-user-04",
            "essayText": oversized,
            "submissionType": "task2",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_wr05_cache_hit_on_repeat_submission(evaluation_client):
    client, runner, _langfuse, _trace = evaluation_client

    payload = {
        "userId": "wr-user-05",
        "essayText": "Caching validation for the same essay text should return from_cache on second call.",
        "submissionType": "task2",
        "examType": "IELTS Writing",
    }
    # Create essay, then evaluate by id twice to exercise cache on streaming endpoint
    create = client.post("/essays", json=payload)
    assert create.status_code == 201
    essay_id = create.json()["id"]

    first_resp = client.post(f"/essays/{essay_id}/evaluate")
    assert first_resp.status_code == 200
    events = _parse_sse(first_resp.text)
    complete = [data for name, data in events if name == "complete"][0]
    assert complete["from_cache"] is False

    # Second call should replay cached evaluation
    second_resp = client.post(f"/essays/{essay_id}/evaluate")
    assert second_resp.status_code == 200
    events2 = _parse_sse(second_resp.text)
    complete2 = [data for name, data in events2 if name == "complete"][0]
    assert complete2["from_cache"] is True

    # Ensure the runner was invoked only for the first evaluation (4 calls)
    assert len(runner.calls) == 4


@pytest.mark.asyncio
async def test_wr06_langfuse_trace_root_and_four_child_spans(evaluation_client):
    client, _runner, langfuse, trace = evaluation_client

    create = client.post(
        "/essays",
        json={
            "userId": "wr-user-06",
            "essayText": "Trace test for Langfuse spans.",
            "submissionType": "task2",
        },
    )
    assert create.status_code == 201
    essay_id = create.json()["id"]

    resp = client.post(f"/essays/{essay_id}/evaluate")
    assert resp.status_code == 200

    # The Langfuse client should be asked to create one top-level observation
    langfuse.start_observation.assert_called_once()
    # The returned root trace's start_observation should be used to create the 4 child spans
    assert trace.start_observation.call_count == 4

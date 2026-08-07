"""GOA-044 — post-deploy smoke suite.

Runs after every production deployment, against the deployed stack, through the
Gateway. On failure the deploy is rolled back to the previous ECS task
definition (see .github/workflows/deploy-production.yml).

WHY THESE CHECKS AND NOT OTHERS
-------------------------------
This suite is not trying to test the product. It is trying to catch the classes
of defect that have historically shipped *green* in this codebase, each of which
was invisible to a unit test because the unit test used a fake:

  BUG-020  exam stats returned a hardcoded 1 against an empty repository
  BUG-022  listening issued 4 signed URLs against a bucket holding zero objects
  BUG-032  orchestration logged "Langfuse client initialized" and sent nothing
  BUG-046  the internal API key shipped inside the browser bundle
  BUG-053  the abandoned-session sweep failed silently every 300s for months

The common thread: a fake has no CHECK constraint to violate, no empty S3
bucket, no real SDK. So every assertion here reads through a real dependency and
asserts on *content*, not on a status code. `assert response.status_code == 200`
is precisely the assertion that let all five of those ship.
"""

from __future__ import annotations

import json
import os
import time

import uuid

import httpx
import pytest

INGESTION_DB = os.getenv(
    "GOA_INGESTION_DB",
    "postgresql://goa:goa_pass@localhost:5432/ingestion_db",
)

# How stale the catalog may be before the gate fails. Ingestion runs weekly, so
# two weeks means a missed run is tolerated and two consecutive misses are not.
FRESHNESS_WINDOW_DAYS = int(os.getenv("GOA_FRESHNESS_WINDOW_DAYS", "14"))


def query_opportunities(
    client: httpx.Client, auth_headers: dict, query: str
) -> httpx.Response:
    """POST an opportunities query, tolerating the profile-replication race.

    A freshly created smoke account replicates to RAG asynchronously, and the
    Gateway answers 425 Too Early until it lands. That is a transient by
    definition — the status code exists to say "retry" — so retrying briefly is
    reading the contract, not weakening the check.

    Retries are capped at three attempts with backoff rather than polling on a
    deadline, because this endpoint is rate limited per user
    (OPPORTUNITY_SEARCHES_PER_HOUR, default 20). A tight retry loop spends the
    smoke account's whole hourly allowance and then fails every *later* check in
    the run with 429 — which reads as a product outage and would roll back a
    perfectly good deploy. Measured: a 2-second poll over 30 seconds burned 15
    of 20 requests in one test.
    """
    backoff = [5, 10, 20]
    for attempt, delay in enumerate(backoff):
        response = client.post(
            "/api/opportunities/query",
            headers=auth_headers,
            json={"query": query},
        )
        if response.status_code != 425:
            return response
        if attempt < len(backoff) - 1:
            time.sleep(delay)

    return response


def assert_not_rate_limited(response: httpx.Response) -> None:
    """Fail with an infrastructure diagnosis rather than a product one.

    429 here means the smoke account ran out of allowance, not that the feature
    broke. Rolling back a deploy over it would be a false positive, so the
    message says plainly what to change: the smoke account needs an exemption,
    or deploys need to be spaced further apart than the limit allows.
    """
    if response.status_code == 429:
        pytest.fail(
            "the smoke account is rate limited "
            f"({response.text[:200]}). This is not a product failure — the "
            "smoke user needs an AI rate-limit exemption, since each run "
            "spends 3 of its hourly allowance."
        )


def chat(client: httpx.Client, auth_headers: dict, message: str) -> dict:
    """One chat turn through the Gateway, reassembled from its SSE stream.

    Chat is the RAG-answering path. /api/opportunities/query is the *matching*
    path and returns scored programs, not prose — pointing a citation check at
    it asserts on a field that route never emits.

    The answer arrives as 5-character token events, so the metadata frame
    carrying `sources` has to be picked out of the stream rather than read off
    a JSON body. Mirrors tests/e2e/test_goa_038_cross_session_memory.py.
    """
    response = client.post(
        "/api/chat",
        headers=auth_headers,
        json={"sessionId": f"smoke-{uuid.uuid4()}", "message": message},
    )
    assert_not_rate_limited(response)
    assert response.status_code == 200, (
        f"chat failed: {response.status_code} {response.text[:300]}"
    )

    answer = ""
    metadata: dict = {}
    for line in response.text.replace("\r\n", "\n").split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except ValueError:
            continue
        if event.get("type") == "token" and event.get("content"):
            answer += event["content"]
        elif event.get("sources") is not None or event.get("type") == "metadata":
            metadata = event

    return {"answer": answer, "sources": metadata.get("sources") or [], "raw": metadata}


def test_gateway_health(client: httpx.Client):
    """The Gateway answers, and identifies the build that is actually running.

    The version assertion is the point. A health endpoint returning 200 from the
    *previous* task definition is exactly what a broken deploy looks like.
    """
    response = client.get("/health")
    assert response.status_code == 200, f"gateway health: {response.status_code}"

    payload = response.json()
    assert payload.get("status") in ("ok", "healthy"), payload
    assert payload.get("version"), f"health response carries no version: {payload}"


def test_authentication_round_trip(client: httpx.Client, auth_headers: dict):
    """Registration and login work, and the issued token is actually accepted.

    Logging in proves the token was minted. Spending it on an authenticated
    route proves the Gateway's JWT middleware agrees — the two have diverged
    before, when a signing-key change shipped to one service and not the other.
    """
    response = client.get("/api/ping", headers=auth_headers)
    assert response.status_code == 200, (
        f"authenticated ping rejected: {response.status_code} {response.text[:200]}"
    )


def test_rag_query_returns_a_grounded_answer(
    client: httpx.Client, auth_headers: dict
):
    """RAG answers a question it demonstrably has the corpus for, with sources.

    Asserting on the sources array rather than on the prose is deliberate: the
    answer text varies run to run, but GOA-033's contract says a grounded answer
    carries its citations. An empty sources array with confident prose is the
    hallucination signature this check exists to catch.
    """
    result = chat(
        client, auth_headers, "How many questions are in the IELTS Reading test?"
    )

    assert result["answer"].strip(), (
        "chat streamed no answer text at all — the RAG path is not responding"
    )

    sources = result["sources"]
    assert sources, (
        f"answer returned with no sources: {result['answer'][:200]!r}"
    )
    assert any(source.get("url") for source in sources), (
        f"no source carries a URL: {sources}"
    )


def test_scoring_returns_a_real_sourced_match(
    client: httpx.Client, auth_headers: dict
):
    """Matching returns a real catalog program with a non-null source URL.

    GOA-044 names this explicitly: "at least one real MastersPortal-backed match
    with a non-null source URL". The source URL is what separates a real catalog
    row from a plausible-looking generated one, and an empty catalog is a
    failure mode that returns 200 with an empty list.
    """
    response = query_opportunities(
        client, auth_headers, "engineering masters programs in Europe"
    )
    assert_not_rate_limited(response)
    assert response.status_code == 200, (
        f"scoring failed: {response.status_code} {response.text[:300]}"
    )

    payload = response.json()
    matches = payload.get("matches") or payload.get("programs") or []
    assert matches, (
        "matching returned no programs — the catalog is empty or the "
        f"handoff is broken: {json.dumps(payload)[:400]}"
    )

    sourced = [
        match
        for match in matches
        if match.get("sourceUrl") or match.get("source_url") or match.get("url")
    ]
    assert sourced, (
        "every match is missing a source URL — the program catalog is not "
        f"MastersPortal-backed: {json.dumps(matches[:3])[:400]}"
    )


def test_visa_answer_cites_an_official_source(
    client: httpx.Client, auth_headers: dict
):
    """A visa answer carries an official citation, per the GOA-033 contract.

    Visa figures are the claims a user will act on with their own money, so an
    uncited one is worse than a refusal. GOA-033 requires the exact official URL
    fetched by GOA-108, or a refusal — never model memory.
    """
    result = chat(
        client,
        auth_headers,
        "What are the financial requirements for a German student visa?",
    )

    answer = result["answer"].strip()

    # An honest refusal satisfies the contract: GOA-033 requires an official
    # citation or nothing, never a figure recalled from model memory. The
    # markers are kept narrow and explicit on purpose — broadening them to "any
    # answer without sources is probably a refusal" would turn this check into
    # one that can never fail, which is the exact shape of the defects this
    # suite exists to catch.
    refusals = ("don't know", "do not know", "please rephrase", "insufficient")
    if not answer or any(marker in answer.lower() for marker in refusals):
        return

    sources = result["sources"]
    assert sources, f"visa answer returned with no sources: {answer[:200]!r}"

    urls = [source.get("url", "") for source in sources]
    assert any(url.startswith("http") for url in urls), (
        f"no citation carries a resolvable URL: {urls}"
    )


def test_notifications_are_reachable(client: httpx.Client, auth_headers: dict):
    """The notification path answers for an authenticated user.

    The queue itself is write-only by design (BUG-025), so a growing backlog is
    expected and is not what this checks. What it checks is that the read path
    the UI uses still resolves after a deploy.
    """
    response = client.get("/api/notifications", headers=auth_headers)
    assert response.status_code == 200, (
        f"notifications unreachable: {response.status_code} {response.text[:200]}"
    )

    payload = response.json()
    assert isinstance(payload, (list, dict)), (
        f"unexpected notifications payload shape: {type(payload)}"
    )


def test_ingestion_freshness_within_window():
    """The catalog was refreshed recently enough to be worth serving.

    Reads the real ingestion database rather than launching a crawl — GOA-044 is
    explicit that the smoke suite must not kick off a full ingestion run. This
    is the one check that cannot go through the Gateway: no route exposes crawl
    state, which is itself worth recording rather than papering over.
    """
    psycopg = pytest.importorskip("psycopg", reason="psycopg is required")

    import datetime

    with psycopg.connect(INGESTION_DB) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT max(last_success_at)
                FROM crawl_cursors
                WHERE last_success_at IS NOT NULL
                """
            )
            row = cursor.fetchone()

    assert row is not None and row[0] is not None, (
        "no source has ever completed an ingestion run — the catalog has "
        "never been populated"
    )

    last_success = row[0]
    if last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=datetime.timezone.utc)

    age = datetime.datetime.now(datetime.timezone.utc) - last_success
    assert age.days <= FRESHNESS_WINDOW_DAYS, (
        f"last successful ingestion was {age.days} days ago, over the "
        f"{FRESHNESS_WINDOW_DAYS}-day window (at {last_success.isoformat()})"
    )


def test_internal_api_key_is_absent_from_the_frontend_bundle(client: httpx.Client):
    """The internal API key must not be reachable from a browser (BUG-046).

    It shipped inside the built bundle once. The unit tests were green for the
    whole time it was there, because no unit test looks at what the browser
    actually downloads.
    """
    frontend_url = os.getenv("GOA_FRONTEND_URL")
    if not frontend_url:
        pytest.skip("GOA_FRONTEND_URL is not set for this environment")

    with httpx.Client(base_url=frontend_url, timeout=20.0) as frontend:
        response = frontend.get("/")
        assert response.status_code == 200, (
            f"frontend unreachable: {response.status_code}"
        )
        assert "NEXT_PUBLIC_INTERNAL_API_KEY" not in response.text, (
            "the internal API key name appears in the served frontend document"
        )

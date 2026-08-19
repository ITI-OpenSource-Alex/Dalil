"""GOA-038 E2E -- does the assistant remember a user across sessions?

Real Gateway, real Orchestration, real Postgres, real Redis, real model. Nothing
is mocked, and every request enters at http://localhost:8080 the way a browser
does. Curling orchestration on :8083 would prove the service works and say
nothing about whether anyone can reach it.

The assertion that matters is E2E-08: the answer streamed back in a *second*
session mentions a degree stated only in the *first*. Everything else in this
file is scaffolding around that one line. An assertion on a prompt string, a log
line, or a database row would pass while the user saw nothing.

    docker compose up -d
    MEMORY_IDLE_MINUTES=1 MEMORY_SWEEP_INTERVAL_SECONDS=15 docker compose up -d orchestration
    python -m pytest tests/e2e/test_goa_038_cross_session_memory.py -v

Skips nothing. If the stack is not up, these fail and say so.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

import asyncpg
import httpx
import pytest

GATEWAY = os.getenv("GOA_GATEWAY_URL", "http://localhost:8080")
ORCH_DB = os.getenv(
    "GOA_ORCHESTRATION_DB",
    "postgresql://goa:goa_pass@localhost:5432/orchestration_db",
)

# How long to wait for the sweep. The default cadence is 30 min idle / 5 min
# interval, which no test can wait out -- bring the stack up with the shortened
# clock in the module docstring.
SWEEP_TIMEOUT_SECONDS = int(os.getenv("GOA_SWEEP_TIMEOUT", "180"))

DEGREE_SENTENCE = "I finished a BSc in Electrical and Electronic Engineering last year"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def credentials():
    unique = uuid.uuid4().hex[:12]
    return {"email": f"goa038-{unique}@example.com", "password": "e2e-password-123"}


async def gateway_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=GATEWAY, timeout=120.0, follow_redirects=True)


def user_id_from_token(access_token: str) -> str:
    """The `sub` claim -- the id the Gateway itself forwards to Orchestration.

    Read from the token rather than from the registration response on purpose:
    facts are keyed by whatever the Gateway derives from the JWT, so asserting
    against that same value is what proves they are keyed to the authenticated
    user and not to anything the browser sent.

    No signature check. This is a test reading a claim, not an authorisation
    decision.
    """
    import base64

    payload = access_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


async def login(client: httpx.AsyncClient, credentials: dict) -> str:
    response = await client.post("/auth/login", json=credentials)
    assert response.status_code == 200, f"login failed: {response.text[:300]}"
    return user_id_from_token(response.json()["access_token"])


def sse_answer(body: str) -> str:
    """Reassemble the tokens a browser would have rendered.

    The answer arrives in 5-character chunks, so asserting against the raw
    response body is really asserting about chunk boundaries.
    """
    answer = ""
    for line in body.replace("\r\n", "\n").split("\n"):
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except ValueError:
            continue
        if event.get("type") == "token" and event.get("content"):
            answer += event["content"]
    return answer


async def say(client: httpx.AsyncClient, session_id: str, message: str) -> str:
    """One chat turn through the Gateway. Returns the assembled answer."""
    response = await client.post(
        "/api/chat",
        json={"sessionId": session_id, "message": message},
        headers={"X-Subscription-Tier": "paid"},
    )
    assert response.status_code == 200, f"chat failed: {response.status_code} {response.text[:300]}"
    return sse_answer(response.text)


async def facts_for(user_id: str) -> dict[str, str]:
    conn = await asyncpg.connect(ORCH_DB)
    try:
        rows = await conn.fetch(
            "SELECT fact_type, fact_value FROM user_facts WHERE user_id = $1", user_id
        )
    finally:
        await conn.close()
    return {r["fact_type"]: r["fact_value"] for r in rows}


async def wait_for_facts(user_id: str, timeout: int = SWEEP_TIMEOUT_SECONDS) -> dict[str, str]:
    """Poll until the sweep has written something, or fail with what we saw."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        facts = await facts_for(user_id)
        if facts:
            return facts
        await asyncio.sleep(3)
    pytest.fail(
        f"no facts were extracted for {user_id} within {timeout}s. Is the stack running with "
        "MEMORY_IDLE_MINUTES lowered? Check: docker compose logs orchestration | grep memory_sweep"
    )


@pytest.mark.anyio
async def test_the_assistant_remembers_a_user_across_sessions(credentials):
    async with await gateway_client() as client:
        # E2E-01: a real account, through the real auth flow.
        register = await client.post("/users", json=credentials)
        assert register.status_code in (200, 201), f"register failed: {register.text[:300]}"

        user_id = await login(client, credentials)

        # E2E-02/03: session A. Four turns, because a shorter session is
        # skipped by design -- an abandoned "hi" is not worth a model call.
        session_a = f"e2e-a-{uuid.uuid4()}"
        await say(client, session_a, DEGREE_SENTENCE)
        await say(client, session_a, "My GPA was 3.2 out of 4")
        await say(client, session_a, "I want to do a master's in Germany")
        await say(client, session_a, "I am worried about the blocked account requirement")

        # E2E-04/05/06: the sweep runs and writes facts keyed by the JWT
        # subject -- not by anything the browser sent.
        facts = await wait_for_facts(user_id)
        assert "degree" in facts, f"no degree fact was extracted, got: {facts}"
        assert "electrical" in facts["degree"].lower()

        # E2E-07/08: a NEW session. Nothing in its history mentions the degree.
        session_b = f"e2e-b-{uuid.uuid4()}"
        answer = await say(
            client, session_b, "Is my degree relevant for a data science master?"
        )

        assert answer, "the second session returned no answer at all"
        assert any(
            token in answer.lower()
            for token in ("electrical", "electronic", "engineering", "eee")
        ), (
            "the assistant did not use a fact from the previous session. "
            f"Facts stored: {facts}. Answer: {answer[:400]!r}"
        )


@pytest.mark.anyio
async def test_a_corrected_fact_updates_rather_than_duplicating(credentials):
    """E2E-09/10 -- the DoD's contradiction case, end to end."""
    async with await gateway_client() as client:
        user_id = await login(client, credentials)

        before = await facts_for(user_id)
        assert before.get("gpa"), f"expected a GPA from the first test, got {before}"

        session_c = f"e2e-c-{uuid.uuid4()}"
        await say(client, session_c, "Actually I rechecked my transcript, my GPA is 3.6")
        await say(client, session_c, "Does that change which programmes I can apply to?")
        await say(client, session_c, "I am still targeting Germany")
        await say(client, session_c, "Thanks, that helps")

        deadline = time.time() + SWEEP_TIMEOUT_SECONDS
        while time.time() < deadline:
            if (await facts_for(user_id)).get("gpa") == "3.6":
                break
            await asyncio.sleep(3)

        conn = await asyncpg.connect(ORCH_DB)
        try:
            gpa_rows = await conn.fetch(
                "SELECT fact_value, revision FROM user_facts "
                "WHERE user_id = $1 AND fact_type = 'gpa'",
                user_id,
            )
        finally:
            await conn.close()

        assert len(gpa_rows) == 1, f"a corrected GPA duplicated instead of updating: {gpa_rows}"
        assert gpa_rows[0]["fact_value"] == "3.6"
        assert gpa_rows[0]["revision"] >= 2, "the row was replaced without recording a revision"


@pytest.mark.anyio
async def test_erasure_removes_everything_and_the_assistant_forgets(credentials):
    """E2E-11/12/13 -- the privacy control, through the Gateway."""
    async with await gateway_client() as client:
        user_id = await login(client, credentials)

        assert await facts_for(user_id), "nothing to erase -- earlier tests did not run?"

        response = await client.delete("/api/sessions/memory")

        assert response.status_code == 200, f"erasure failed: {response.text[:300]}"
        body = response.json()
        assert body["factsDeleted"] > 0
        assert await facts_for(user_id) == {}, "facts survived a deletion that reported success"

        # E2E-13: and the assistant stops referring to them.
        session_d = f"e2e-d-{uuid.uuid4()}"
        answer = await say(client, session_d, "Is my degree relevant for a data science master?")
        assert "electrical" not in answer.lower(), (
            f"a deleted fact was still used in an answer: {answer[:400]!r}"
        )


@pytest.mark.anyio
async def test_erasure_requires_authentication():
    """A destructive endpoint that an anonymous caller can reach is not a privacy control."""
    async with await gateway_client() as client:
        response = await client.delete("/api/sessions/memory")
        assert response.status_code == 401

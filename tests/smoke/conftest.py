"""Shared fixtures for the GOA-044 post-deploy smoke suite.

Everything here talks to the Gateway. A smoke check that curls a service on its
own port proves the service is alive and says nothing about whether the
deployment a user just received actually works — which is the only question a
post-deploy gate exists to answer.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

GATEWAY = os.getenv("GOA_GATEWAY_URL", "http://localhost:8080")

# The smoke account is created once and reused forever (GOA-044: "Tests use a
# dedicated smoke-test user account (never deleted)"). Registering a fresh user
# on every deploy would leave a trail of accounts in production and would make
# the suite's own history unreadable.
SMOKE_EMAIL = os.getenv("GOA_SMOKE_EMAIL", "smoke-test@goa.app")
SMOKE_PASSWORD = os.getenv("GOA_SMOKE_PASSWORD", "SmokeTest!2026pw")

# The whole suite has a 120-second budget. Individual requests get a slice of it
# generous enough for a cold Fargate task to answer, but short enough that a
# hung dependency fails the gate instead of hanging it.
REQUEST_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=GATEWAY, timeout=REQUEST_TIMEOUT) as http_client:
        yield http_client


@pytest.fixture(scope="session")
def smoke_token(client: httpx.Client) -> str:
    """Log the permanent smoke user in, registering it the first time only.

    Deliberately does not skip when auth is down. A smoke suite that skips its
    way to green when the thing it guards is broken is the exact failure this
    ticket exists to stop.
    """
    login = client.post(
        "/auth/login",
        json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD},
    )

    if login.status_code == 200:
        return _access_token(login)

    # 401 means the account does not exist yet in this environment (first deploy
    # against a fresh database). Any other status is a real auth failure and
    # must surface rather than be papered over with a registration attempt.
    assert login.status_code in (400, 401), (
        f"login failed unexpectedly: {login.status_code} {login.text[:300]}"
    )

    register = client.post(
        "/users",
        json={
            "email": SMOKE_EMAIL,
            "password": SMOKE_PASSWORD,
            "fullName": "GOA Smoke Test",
        },
    )
    assert register.status_code in (200, 201, 409), (
        f"smoke user registration failed: "
        f"{register.status_code} {register.text[:300]}"
    )

    login = client.post(
        "/auth/login",
        json={"email": SMOKE_EMAIL, "password": SMOKE_PASSWORD},
    )
    assert login.status_code == 200, (
        f"login after registration failed: "
        f"{login.status_code} {login.text[:300]}"
    )
    return _access_token(login)


def _access_token(response: httpx.Response) -> str:
    payload = response.json()
    for key in ("accessToken", "access_token", "token"):
        if payload.get(key):
            return payload[key]
    for container in ("data", "tokens"):
        nested = payload.get(container) or {}
        for key in ("accessToken", "access_token", "token"):
            if nested.get(key):
                return nested[key]
    raise AssertionError(f"no access token in login response: {payload}")


@pytest.fixture(scope="session")
def auth_headers(client: httpx.Client, smoke_token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {smoke_token}",
        # A correlation id per run makes a failed gate traceable through every
        # downstream log without guessing which request was the smoke test.
        "X-Correlation-ID": f"smoke-{uuid.uuid4()}",
    }
    _ensure_profile(client, headers)
    return headers


def _ensure_profile(client: httpx.Client, headers: dict[str, str]) -> None:
    """Give the smoke account a profile, once, and let it replicate to RAG.

    Registering an account is not enough. The RAG-backed routes answer
    425 Too Early until a *profile* has propagated over the user-events queue,
    and registration alone emits no such event — so a smoke user that has never
    completed onboarding 425s forever and the gate never reaches its real
    assertions.

    This is idempotent: on every run after the first the profile already exists
    and the PUT is a no-op update.
    """
    profile = client.get("/api/profile", headers=headers)
    if profile.status_code == 200:
        body = profile.json() or {}
        if body.get("targetCountry") or body.get("target_country"):
            return

    client.put(
        "/api/profile",
        headers=headers,
        json={
            "fullName": "GOA Smoke Test",
            "targetCountry": "Germany",
            "fieldOfStudy": "Engineering",
            "degreeLevel": "masters",
            "ieltsScore": 7.0,
            "cgpa": 3.4,
        },
    )

    # Replication is asynchronous. Wait once here, at session scope, rather than
    # letting each test discover the lag independently — the query endpoint is
    # rate limited per user and polling it burns the account's hourly allowance.
    time.sleep(3)


@pytest.fixture(scope="session", autouse=True)
def suite_budget():
    """Fail the run if the suite breaks its 120-second contract.

    GOA-044 specifies "runs within 2 minutes" as an acceptance criterion, so it
    is asserted rather than hoped for. A gate that slows down every deploy stops
    being run, and a smoke suite nobody runs protects nothing.
    """
    started = time.monotonic()
    yield
    elapsed = time.monotonic() - started
    assert elapsed < 120, (
        f"smoke suite took {elapsed:.1f}s, over its 120s budget"
    )

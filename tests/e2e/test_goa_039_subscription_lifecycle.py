"""GOA-039 E2E -- can a user actually upgrade, use, and cancel Dalil Pro?

Real Gateway, real User service, real Postgres, real Redis. Nothing is mocked,
and every request enters at http://localhost:8080 the way a browser does. The
billing routes exist to be reached from outside; curling the User service on
:8081 would prove the handler works and say nothing about whether anyone can
reach it.

There is no payment provider. This project uses a self-contained DEMO payment:
the checkout page is served by the frontend and the outcome is decided by the
User service from a table of demo card numbers. That means the whole lifecycle
is genuinely testable here -- including the two card scenarios in GOA-039's
definition of done, which would otherwise need an external account:

    4242424242424242  -> succeeds
    4000000000009995  -> declined, insufficient funds

Demo billing hands out the paid tier without taking money, so the User service
refuses to serve these routes when NODE_ENV=production. That refusal is
asserted at the unit level (billing.service.spec.ts); this file exercises the
development path.

    docker compose up -d
    python -m pytest tests/e2e/test_goa_039_subscription_lifecycle.py -v

Skips nothing. If the stack is not up, these fail and say so.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

GATEWAY = os.getenv("GOA_GATEWAY_URL", "http://localhost:8080")
FRONTEND_ORIGIN = os.getenv("GOA_FRONTEND_ORIGIN", "http://localhost:3000")

SUCCESS_CARD = "4242424242424242"
DECLINE_CARD = "4000000000009995"

# Every route the Gateway puts behind subscriptionMiddleware.RequirePaid. The
# gate is shared, so testing one of them proves very little about the others
# actually being registered inside the group.
PAID_ROUTES = [
    ("GET", "/api/exam/progress"),
    ("POST", "/api/exam/sessions"),
    ("POST", "/api/writing/cv/review"),
]

RETURN_URLS = {
    "successUrl": f"{FRONTEND_ORIGIN}/billing/success",
    "cancelUrl": f"{FRONTEND_ORIGIN}/pricing?checkout=cancelled",
}


def new_account() -> tuple[httpx.Client, str]:
    """A brand-new, signed-in, free-tier account, created through the Gateway.

    Function-scoped on purpose. The Gateway rate-limits /api at 60 requests per
    user per minute (middleware/rate_limit.go), and a suite that drove the whole
    lifecycle through one account spent that budget and started failing on 429 --
    the limiter working exactly as intended. A fresh account per test also means
    every test starts from a known free tier without a reset dance.
    """
    unique = uuid.uuid4().hex[:12]
    credentials = {
        "email": f"goa039-{unique}@example.com",
        "password": "e2e-password-123",
    }

    client = httpx.Client(base_url=GATEWAY, timeout=30.0)
    registered = client.post("/users", json=credentials)
    assert registered.status_code < 400, registered.text
    user_id = registered.json()["id"]

    signed_in = client.post("/auth/login", json=credentials)
    assert signed_in.status_code == 200, signed_in.text
    assert client.cookies.get("access_token")

    return client, user_id


@pytest.fixture
def client() -> httpx.Client:
    session, _ = new_account()
    try:
        yield session
    finally:
        # Not `with`: the client has already issued the register/login
        # requests, and httpx refuses to be re-entered once opened.
        session.close()


def tier(client: httpx.Client) -> str:
    response = client.get("/api/profile")
    assert response.status_code == 200, response.text
    return response.json()["subscriptionTier"]


def open_checkout(client: httpx.Client) -> str:
    """Starts a checkout and returns the single-use token from its URL."""
    response = client.post("/api/billing/create-checkout", json=RETURN_URLS)
    assert response.status_code == 200, response.text

    url = response.json()["url"]
    assert url.startswith(f"{FRONTEND_ORIGIN}/billing/demo-checkout"), url

    token = parse_qs(urlparse(url).query)["session"][0]
    assert re.fullmatch(r"[a-f0-9]{64}", token), token
    return token


def confirm(client: httpx.Client, token: str, card: str) -> httpx.Response:
    return client.post(
        "/api/billing/demo/confirm", json={"token": token, "cardNumber": card}
    )


# --------------------------------------------------------------------------
# The paywall, before anyone upgrades
# --------------------------------------------------------------------------


def test_new_account_is_free(client):
    assert tier(client) == "free"


@pytest.mark.parametrize("method,path", PAID_ROUTES)
def test_paid_routes_are_gated_for_a_free_user(client, method, path):
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "subscription_required"


def test_the_gate_points_at_a_route_that_exists(client):
    # /upgrade, the old default, is not a page in this product -- the upgrade
    # CTA led to a 404 in a new tab.
    response = client.get("/api/exam/progress")
    assert response.json()["upgradeUrl"] == "/pricing"


# --------------------------------------------------------------------------
# Billing endpoint authentication and open-redirect protection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/billing/create-checkout",
        "/api/billing/demo/confirm",
        "/api/billing/cancel",
    ],
)
def test_billing_requires_a_session(path):
    with httpx.Client(base_url=GATEWAY, timeout=30.0) as anonymous:
        response = anonymous.post(path, json={})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "success_url",
    [
        "https://evil.test/x",
        "https://localhost:3000@evil.test/",  # userinfo smuggling
        "javascript:alert(1)",
        "//evil.test/x",
        "http://localhost:3001/x",  # port mismatch
    ],
)
def test_checkout_refuses_a_return_url_we_do_not_own(client, success_url):
    # The return URL decides both where the browser lands afterwards and which
    # origin serves the payment form.
    response = client.post(
        "/api/billing/create-checkout",
        json={"successUrl": success_url, "cancelUrl": RETURN_URLS["cancelUrl"]},
    )
    assert response.status_code == 400, response.text


# --------------------------------------------------------------------------
# The upgrade, and what it unlocks
# --------------------------------------------------------------------------


def test_opening_a_checkout_grants_nothing(client):
    open_checkout(client)
    assert tier(client) == "free"


def test_successful_payment_upgrades_and_unlocks_every_paid_route(client):
    token = open_checkout(client)

    started = time.monotonic()
    response = confirm(client, token, SUCCESS_CARD)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert response.json()["redirectUrl"] == RETURN_URLS["successUrl"]

    # Persisted, not just cached.
    assert tier(client) == "paid"

    # And the Gateway's cached "free" is gone. Without the DEL in
    # UsersService.updateSubscription this stays 403 for SUBSCRIPTION_CACHE_TTL
    # (5 minutes by default) and the acceptance criterion is unreachable.
    for method, path in PAID_ROUTES:
        gated = client.request(method, path, json={} if method == "POST" else None)
        assert not (
            gated.status_code == 403
            and gated.json().get("error") == "subscription_required"
        ), f"{path} still gated after upgrade"

    assert time.monotonic() - started < 5.0, "paid access took longer than 5s"


def test_declined_payment_leaves_the_user_free_and_the_gate_closed(client):
    token = open_checkout(client)

    response = confirm(client, token, DECLINE_CARD)

    # A decline is a normal outcome the page renders, not a transport error.
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "declined"
    assert "insufficient funds" in response.json()["message"].lower()

    assert tier(client) == "free"
    gated = client.get("/api/exam/progress")
    assert gated.status_code == 403
    assert gated.json()["error"] == "subscription_required"


def test_an_unknown_card_is_declined(client):
    token = open_checkout(client)

    response = confirm(client, token, "1234567812345678")

    assert response.status_code == 200
    assert response.json()["status"] == "declined"
    assert tier(client) == "free"


def test_a_checkout_token_cannot_be_spent_twice(client):
    # Single-use is what stops a replayed confirm from re-granting a tier the
    # user has since cancelled.
    token = open_checkout(client)

    assert confirm(client, token, SUCCESS_CARD).json()["status"] == "succeeded"
    assert confirm(client, token, SUCCESS_CARD).status_code == 400
    assert tier(client) == "paid"


def test_a_declined_attempt_also_spends_its_token(client):
    token = open_checkout(client)

    assert confirm(client, token, DECLINE_CARD).json()["status"] == "declined"
    # Retrying needs a fresh checkout, so a declined token cannot be reused
    # with a different card.
    assert confirm(client, token, SUCCESS_CARD).status_code == 400
    assert tier(client) == "free"


def test_a_forged_token_upgrades_nobody(client):
    forged = "f" * 64

    assert confirm(client, forged, SUCCESS_CARD).status_code == 400
    assert tier(client) == "free"


def test_a_malformed_token_is_rejected_by_validation(client):
    response = confirm(client, "not-a-token", SUCCESS_CARD)

    assert response.status_code == 422, response.text
    assert tier(client) == "free"


def test_an_already_paid_account_cannot_open_a_second_checkout(client):
    token = open_checkout(client)
    confirm(client, token, SUCCESS_CARD)
    assert tier(client) == "paid"

    response = client.post("/api/billing/create-checkout", json=RETURN_URLS)
    assert response.status_code == 409, response.text


# --------------------------------------------------------------------------
# Cross-account safety
# --------------------------------------------------------------------------


def test_a_checkout_token_cannot_be_settled_by_another_account(client):
    """The decisive test: holding somebody else's token must upgrade nobody."""
    victim_token = open_checkout(client)

    other, _ = new_account()
    try:
        response = other.post(
            "/api/billing/demo/confirm",
            json={"token": victim_token, "cardNumber": SUCCESS_CARD},
        )
        assert response.status_code == 400, response.text
        assert other.get("/api/profile").json()["subscriptionTier"] == "free"
    finally:
        other.close()

    # And the victim gained nothing either.
    assert tier(client) == "free"


# --------------------------------------------------------------------------
# Cancellation
# --------------------------------------------------------------------------


def test_cancellation_downgrades_and_closes_the_gate_again(client):
    token = open_checkout(client)
    confirm(client, token, SUCCESS_CARD)
    assert tier(client) == "paid"

    response = client.post("/api/billing/cancel", json={})
    assert response.status_code == 200, response.text
    assert response.json()["subscriptionTier"] == "free"
    assert tier(client) == "free"

    # Immediately, not after the TTL -- otherwise a cancelled subscriber keeps
    # paid access for five more minutes.
    gated = client.get("/api/exam/progress")
    assert gated.status_code == 403
    assert gated.json()["error"] == "subscription_required"


def test_cancelling_a_plan_you_do_not_have_is_refused(client):
    response = client.post("/api/billing/cancel", json={})
    assert response.status_code == 409, response.text


def test_a_cancel_request_cannot_name_another_user(client):
    # Whose subscription is cancelled follows from the session, so a payload
    # naming a victim is simply ignored.
    token = open_checkout(client)
    confirm(client, token, SUCCESS_CARD)

    response = client.post(
        "/api/billing/cancel", json={"userId": str(uuid.uuid4()), "tier": "paid"}
    )
    assert response.status_code == 200
    assert tier(client) == "free"

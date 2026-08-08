# Cross-service E2E tests

Tests that drive a **running stack** through the Gateway, the way a browser
does. Everything here talks to `http://localhost:8080` and never to a service's
own port — a test that curls `:8083` directly proves the service works and says
nothing about whether anyone can reach it.

Created by GOA-038, which was the first ticket to need one. GOA-063 and GOA-081
are expected to add to this directory rather than start a second harness.

GOA-039 added `test_goa_039_subscription_lifecycle.py`, which drives the whole
billing lifecycle — paywall, checkout authorisation, payment, cache
invalidation, cancellation — against the real Gateway, User service, Postgres
and Redis. Billing is a self-contained demo payment, so there is nothing
external to configure and the definition-of-done card scenarios really run:

```bash
docker compose up -d
python -m pytest tests/e2e/test_goa_039_subscription_lifecycle.py -v
```

Every test creates its own account. That is not incidental: the Gateway limits
`/api` to 60 requests per user per minute, and a suite that drove the whole
lifecycle through one account exhausted that budget and started failing on 429.

## What belongs here

- Flows that cross a service boundary and need real dependencies: a real
  database, a real Redis, a real HTTP hop, a real model call.
- Anything whose failure mode is "each service passes its own tests and the
  system still does not work".

## What does not

- Anything a service's own `tests/` directory can cover. These are slow, they
  need the whole stack up, and a suite that is expensive to run is a suite that
  stops being run.

## Running

```bash
cd "$(git rev-parse --show-toplevel)"
docker compose up -d
pip install pytest pytest-asyncio httpx asyncpg redis

# The full stack must be healthy first — these tests assert on real behaviour
# and will fail honestly rather than skip if it is not.
python -m pytest tests/e2e -v
```

Some tests need the sweep to run within the test's lifetime. Bring the stack up
with a shortened clock for those:

```bash
MEMORY_IDLE_MINUTES=1 MEMORY_SWEEP_INTERVAL_SECONDS=15 docker compose up -d orchestration
```

## Conventions

- **No mocks.** If something needs mocking, it belongs in a service's own suite.
- **Assert on what the client received**, not on logs or database state alone.
  Database checks are supporting evidence; the bytes the browser would have
  rendered are the claim.
- **Clean up after yourself.** These run against a developer's live stack.

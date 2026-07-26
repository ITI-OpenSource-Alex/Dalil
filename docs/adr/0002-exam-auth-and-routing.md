# ADR 0002: Exam Service — Auth Model & Local/Production Routing

* **Status**: Accepted
* **Date**: 2026-07-26
* **Deciders**: Frontend Team (GOA-054), Architecture Team (GOA-071 / GOA-084 / GOA-090)

---

## Context

The Exam Service (`services/exam`, port 8085) was integrated with the frontend in GOA-054. Two architectural decisions arose during that work and need to be documented:

1. **Routing**: The frontend calls the Exam Service directly on port 8085, bypassing the API Gateway. Is this intentional?
2. **Auth model**: The Exam Service uses a static `INTERNAL_API_KEY` header (`X-Internal-API-Key`) for all endpoints, while other services authenticate users via JWT issued by the Gateway (GOA-084 / GOA-090). Is this consistent enough?

---

## Decision 1: Local Dev — Direct Calls to Port 8085

### Options Considered

**Option A — Always route through the Gateway (`:8080`)**
* Pros: Consistent with production topology; JWT auth validated at the Gateway.
* Cons: Adds operational overhead (Gateway must be running) to the inner dev loop; more complex local setup.

**Option B — Direct calls to `:8085` in local development (chosen)**
* Pros: Zero extra dependencies for frontend dev; simpler and faster inner loop.
* Cons: The Gateway is bypassed locally, so local behaviour differs slightly from production.

### Decision

**Option B is the intended local-development pattern.**

The frontend's `NEXT_PUBLIC_EXAM_API_URL` environment variable defaults to `http://localhost:8085`. Developers configure it in `services/frontend/.env.local` and call the Exam Service directly for local work.

In staging and production, all Exam API traffic is routed through the public ALB/Gateway at `/api/exam/*`. The Gateway performs JWT authentication and forwards requests internally to the Exam Service so the Exam port is never publicly exposed. This production routing plan is tracked under **GOA-071**.

---

## Decision 2: Auth Model — Static Internal API Key vs. JWT

### Context

The Exam Service `app/core/security.py` exposes a `validate_internal_api_key` dependency that checks the `X-Internal-API-Key` header against the `INTERNAL_API_KEY` environment variable. This is a static shared secret, which differs from the JWT-based approach used by other GOA services.

### Options Considered

**Option A — Migrate all Exam endpoints to JWT now**
* Pros: Consistent auth model across all services.
* Cons: The Gateway JWT auth work (GOA-084 / GOA-090) is not yet complete; migrating now would block the exam feature on unfinished infrastructure.

**Option B — Keep static `INTERNAL_API_KEY` short-term, migrate to JWT later (chosen)**
* Pros: Unblocks the exam flow immediately; suitable for internal service-to-service calls.
* Cons: Inconsistency in auth model across services until migration is complete.

### Decision

**Option B is the accepted short-term approach.**

* **`/internal/*` endpoints** (e.g., `/internal/question-bank/stats`, `/internal/users/{id}/profile-for-recommendation`): These are service-to-service calls; a static shared key is appropriate and will be **retained permanently**.
* **User-facing endpoints** (`/sessions`, `/exam/reading/start`, etc.): These currently accept `user_id` as a body/query parameter, protected by the same `INTERNAL_API_KEY`. Once GOA-084/GOA-090 lands, a follow-up ticket must:
  1. Add a `validate_jwt_token` dependency for user-facing routes.
  2. Extract `user_id` from the JWT payload instead of the request body.
  3. Keep `validate_internal_api_key` for `/internal/*` routes only.

### Consequences

* Short-term: The frontend sends `X-Internal-API-Key: <NEXT_PUBLIC_INTERNAL_API_KEY>` on all exam requests. This value must match `INTERNAL_API_KEY` on the Exam Service deployment.
* Long-term: A follow-up ticket under GOA-084/GOA-090 scope will migrate user-facing exam endpoints to JWT auth, removing the need for the frontend to send the internal key.

---

## References

* GOA-054 — Exam Service frontend integration
* GOA-048 — Internal API key security
* GOA-049 — Question bank seeding
* GOA-071 — ALB routing plan for production
* GOA-084 / GOA-090 — Gateway JWT authentication work

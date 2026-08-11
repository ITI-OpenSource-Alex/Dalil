"""GOA-036 — provision real accounts for the load test.

Why not `mintjwt`
-----------------
perf/run-speaking-load.sh mints a Gateway-signed token for an arbitrary subject,
which is right for the speaking socket: it needs a valid JWT and nothing else.
It is not enough here. Two of the four scenarios need an account that actually
exists:

  * essay  -> both routes are RequirePaid, so the Gateway resolves the subject's
              subscription against the User service. A minted token for a
              subject with no record cannot be paid.
  * match  -> RAG scores against local_user_profiles, replicated from the User
              service over SQS. No profile, no match: /match answers 425
              forever.

So the pool is registered, profiled and upgraded through the real Gateway, the
same way the GOA-030 journeys do it. This is setup, not measurement, and it runs
before k6 starts so none of it lands on the measured path.

The tokens are written to perf/tokens.json, which k6 reads in init scope.

Usage:
    python perf/provision_load_users.py --count 20 --out perf/tokens.json
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

PASSWORD = "SecurePassword123!"


def suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def provision_one(gateway: str, index: int) -> dict | None:
    """Registers, profiles and upgrades one account. Returns its token."""
    email = f"k6-load-{int(time.time())}-{index}-{suffix()}@example.com"
    try:
        with httpx.Client(base_url=gateway, timeout=60) as client:
            registration = client.post(
                "/users", json={"email": email, "password": PASSWORD}
            )
            if registration.status_code >= 400:
                print(f"  [{index}] register failed {registration.status_code}", file=sys.stderr)
                return None
            user_id = registration.json()["id"]

            login = client.post(
                "/auth/login", json={"email": email, "password": PASSWORD}
            )
            if login.status_code >= 400:
                print(f"  [{index}] login failed {login.status_code}", file=sys.stderr)
                return None
            token = login.json()["access_token"]
            auth = {"Authorization": f"Bearer {token}"}

            # A profile, so /match has something to score. Countries are spread
            # across the pool: one country for every VU would make the whole
            # match scenario a single cache entry and measure Redis.
            countries = ["Germany", "Netherlands", "Italy", "France", "Ireland", "Spain"]
            client.put(
                "/api/profile",
                headers=auth,
                json={
                    "degreeLevel": "bachelor",
                    "gpa": 3.2 + (index % 8) * 0.1,
                    "gpaScale": "4.0",
                    "ieltsScore": 6.0 + (index % 7) * 0.5,
                    "targetCountries": [countries[index % len(countries)]],
                    "fieldOfStudy": "Computer Science" if index % 2 else "Engineering",
                    "ects": 180,
                    "workExperienceYears": index % 4,
                },
            )

            # Paid tier through the real demo billing flow. Not a database
            # write: the subscription cache invalidation and the Gateway's
            # RequirePaid resolution are part of what the essay scenario
            # measures.
            checkout = client.post(
                "/api/billing/create-checkout",
                headers=auth,
                json={"returnUrl": "http://localhost:3000/billing/success"},
            )
            if checkout.status_code < 400:
                session = checkout.json()["url"].split("session=")[-1]
                client.post(
                    "/api/billing/demo/confirm",
                    headers=auth,
                    json={"token": session, "cardNumber": "4242424242424242"},
                )

            return {"index": index, "userId": user_id, "email": email, "token": token}
    except Exception as exc:  # noqa: BLE001
        print(f"  [{index}] provisioning error: {exc}", file=sys.stderr)
        return None


def wait_for_replication(gateway: str, accounts: list[dict], timeout: float = 180.0) -> int:
    """Blocks until /match stops answering 425 for each account.

    Done before k6 starts on purpose. Left to the run, every early iteration
    would record a 425 and the match scenario's first minute would describe SQS
    lag rather than match latency.
    """
    deadline = time.time() + timeout
    pending = list(accounts)
    replicated = 0

    with httpx.Client(base_url=gateway, timeout=120) as client:
        while pending and time.time() < deadline:
            still_pending = []
            for account in pending:
                response = client.post(
                    "/api/opportunities/query",
                    headers={"Authorization": f"Bearer {account['token']}"},
                    json={},
                )
                if response.status_code == 425:
                    still_pending.append(account)
                else:
                    replicated += 1
            pending = still_pending
            if pending:
                time.sleep(2)

    if pending:
        # Reported, not raised. A partially replicated pool still produces a
        # valid run; silently pretending it was complete would not.
        print(
            f"WARNING: {len(pending)} of {len(accounts)} profiles never replicated "
            f"within {timeout}s. The match scenario will record 425s for those VUs "
            "under goa_match_not_replicated.",
            file=sys.stderr,
        )
    return replicated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://localhost:8080")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", default="perf/tokens.json")
    parser.add_argument("--meta-out", default="perf/tokens-meta.json")
    args = parser.parse_args()

    print(f"provisioning {args.count} accounts against {args.gateway} ...")
    started = time.time()

    # Modest parallelism. The Gateway rate-limits per user, not globally, but
    # registration hits the User service and Postgres hard enough that 50
    # simultaneous registrations produce failures that look like defects.
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: provision_one(args.gateway, i), range(args.count)))

    accounts = [account for account in results if account]
    if not accounts:
        print("FATAL: no accounts were provisioned; is the stack up?", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(accounts)}/{args.count} accounts in {time.time() - started:.1f}s")

    print("waiting for profile replication to RAG ...")
    replicated = wait_for_replication(args.gateway, accounts)
    print(f"  {replicated}/{len(accounts)} profiles replicated")

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump([account["token"] for account in accounts], handle)
    with open(args.meta_out, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "requested": args.count,
                "provisioned": len(accounts),
                "replicated": replicated,
                "gateway": args.gateway,
                "userIds": [account["userId"] for account in accounts],
                "emails": [account["email"] for account in accounts],
            },
            handle,
            indent=2,
        )
    print(f"wrote {args.out} ({len(accounts)} tokens) and {args.meta_out}")


if __name__ == "__main__":
    main()

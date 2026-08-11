# GOA-036 — load test against a real AWS staging environment

**Run `20260811T112502Z`.** 10 minutes sustained against `goa-staging` in
AWS account `114403655381`, region `eu-west-1`, entirely through the public ALB.

This is the run the ticket actually asks for. The earlier local-compose run
(`GOA-036-report.md`) stands as the fuller measurement; this one measures a
deployed environment and, more usefully, establishes **what a deployed
environment does and does not do today**.

---

## 1. Headline

| | |
|---|---|
| Target | `https://goa-staging-alb-229162060.eu-west-1.elb.amazonaws.com` (public ALB → ECS Fargate) |
| Duration | 10 minutes, 63 VUs (chat 10, speaking 2, essay 1, match 50) |
| Identities | 50 accounts registered, profiled and (attempted) upgraded through the ALB |
| Catalogue in RDS | **3,805 programmes, 3,979 document chunks, 19 visa requirements, 60 visa sources** |
| Requests | 4,076 HTTP + 2,155 WebSocket attempts |
| **Scenarios that produced a valid measurement** | **1 of 4** |

**Read that last line before any number below.** Only the `match` scenario
measured the system. The other three were blocked by environment defects, and
their latency figures are artefacts of failing fast — reporting them as
performance would be a lie.

---

## 2. What each scenario actually measured

| Scenario | Result | Valid? |
|---|---|---|
| **match** | p50 **389 ms**, p95 **831 ms**, max 5,271 ms — 50 programmes returned every time | ✅ **Yes** |
| **chat** | p50 389 ms, p95 507 ms — but **`goa_chat_source_count` max = 0** | ❌ No — answered with zero sources |
| **essay** | evaluation p50/p95/max all **0 ms**; upload returned 403 | ❌ No — never ran |
| **speaking** | **0 of 2,155 WebSocket upgrades succeeded** | ❌ No — path 404s |

### match — the one real number

```
goa_match_duration_ms      p50 389.3   p90 457.6   p95 830.6   max 5270.6
goa_match_program_count    p50 50      p95 50      max 50
```

Against the **ticket's full specified concurrency of 50 VUs** and the complete
3,805-programme catalogue, `/api/opportunities/query` sustained a **p95 of
831 ms against a 5,000 ms criterion** — comfortably inside it. The batch rewrite
holds up at real catalogue size on real infrastructure.

For comparison, the same scenario on local compose measured p95 2,131 ms. The
deployed environment is **~2.5× faster**, which is what dedicated RDS and
ElastiCache buy over nine containers sharing one laptop.

### chat — 200 OK with nothing in it

Chat returned quickly and returned **no sources at all**, on every single
request. That is not a fast chat; it is the RAG fallback path.

Cause: **the `embeddings` service never started.** Its image is 5.45 GB and the
push to ECR did not complete before the run. RAG cannot embed a query, so
retrieval returns nothing and orchestration falls back to a generic reply.

This is precisely the failure mode the sidecar was added to prevent, caught here
by `goa_chat_source_count` — a status-code check would have recorded 200s and
called it a pass.

### essay — blocked by configuration, not capacity

Upload returned **403 `subscription_required`**, so evaluation never ran and its
timings are all zero. `goa_auth_failures = 111` is this, counted separately from
server errors exactly so it could not be mistaken for one.

Cause: **`BILLING_MODE` is not set anywhere in Terraform.** `.env.example` states
that `demo` "is the only supported value today. Anything else disables the
billing endpoints." With it unset, no account can reach the paid tier, so both
`RequirePaid` essay routes are closed to every user in a deployed environment.

### speaking — every WebSocket upgrade failed

```
goa_speaking_ws_upgrade_success   0 / 2155   (threshold rate>0.99 CROSSED)
ws_connecting                     p50 557 ms  (connect, then immediate close)
```

`GET /api/speaking/ws` through the ALB returns **404**, verified by hand.

Cause: the ALB listener rule at priority 10 routes `/api/speaking/ws` **directly
to the `speaking` target group**, bypassing the Gateway. The speaking service
serves that socket at `/ws`, not `/api/speaking/ws`, so it 404s.

This is worth more than a bug report. That rule also **bypasses the Gateway's
JWT validation at upgrade time** — the exact protection GOA-132 added, and the
same hole GOA-030 closed on the identity side. If the path had happened to
match, the socket would have been reachable with no authentication at all.

---

## 3. Errors and rate limiting

| Metric | Value |
|---|---|
| `goa_server_errors` (5xx / transport) | **3** of 4,076 = **0.07%** |
| `goa_rate_limited` (429) | 3,240 |
| `goa_auth_failures` (401/403) | 111 |
| `goa_match_not_replicated` (425) | 144 |
| `goa_essay_agent_failures` | 0 |
| `goa_speaking_empty_transcripts` | 0 |
| k6 checks | 578 passed / 2,155 failed (all failures are the speaking upgrade) |

**Error rate 0.07%, inside the ticket's <1% criterion.** 429s, 403s and 425s are
counted separately and excluded: a rate limiter refusing traffic, an entitlement
check refusing an unpaid account, and a documented "profile not yet replicated"
contract are all the system behaving correctly.

As on local compose, **the per-feature rate limits were the binding constraint**
— 3,240 of 4,076 requests refused (79%). `OPPORTUNITY_SEARCHES_PER_HOUR = 20`
means 50 users cannot sustain more than 1,000 searches an hour between them.

Only 25 of 50 profiles replicated to RAG within the 180 s provisioning window,
which is why 144 requests hit 425. SQS replication is materially slower against
real SQS than against LocalStack.

---

## 4. Thresholds

| Threshold | Crossed? |
|---|---|
| `goa_match_duration_ms p(95)<5000` | no — **831 ms** |
| `goa_chat_duration_ms p(95)<5000` | no — but the measurement is void (§2) |
| `goa_essay_evaluation_duration_ms p(95)<30000` | no — never ran |
| `goa_speaking_time_to_first_transcript_ms p(95)<45000` | no — never ran |
| `goa_speaking_ws_upgrade_success rate>0.99` | **YES — 0.00** |
| `goa_server_errors count<10` | no — 3 |
| `goa_essay_agent_failures count==0` | no |

k6 exit 99. The one genuine threshold breach is the speaking upgrade.

---

## 5. Environment state at run time

| Service | Running | Notes |
|---|---|---|
| gateway, user, orchestration, rag, writing, exam, speaking, speech | **1–2 / 1–2** | healthy |
| **embeddings** | **0 / 1** | image never finished pushing (5.45 GB) |

Infrastructure: 2× NAT gateway, `db.t3.micro` RDS, `cache.t3.micro` ElastiCache,
1× ALB, ECS Fargate. **All destroyed after this run** — see §7.

> **Caveat on the catalogue line in the run log.** `run-load-test.sh` reads the
> catalogue count from the LOCAL compose Postgres, so the `3805,3793,3979,19` it
> printed is the local figure. The staging figures quoted in §1 come from the
> seeder's own `COPY` output (3,805 / 19 / 60) plus the first seeding run's
> `COPY 3979`. They agree because staging was seeded from that same dump, but
> the script's line is not evidence about staging and should be fixed to read
> from the target environment.

---

## 6. What this run is worth

**It answered the question the local run could not:** does the deployed
architecture work? Partly. One flow is genuinely fast at full specified
concurrency; three are blocked by defects that only exist in a deployed
environment and were therefore invisible to every prior test.

Nine defects were found and fixed getting this far — see
`Docs/GOA_Sprint_4_Tickets.md` (GOA-037) for the full list. Four more are open:

1. **`embeddings` not deployed** — chat and RAG retrieval are non-functional until
   the image is in ECR. Nothing is wrong with the service definition; the upload
   did not finish.
2. **`/api/speaking/ws` ALB rule** — routes past the Gateway to a path the
   speaking service does not serve. Both a functional break and an auth bypass.
   The rule should be deleted so the socket goes through the Gateway like
   everything else.
3. **`BILLING_MODE` unset** — no account can reach the paid tier, so every
   `RequirePaid` route is closed in a deployed environment.
4. **`run-load-test.sh` reads the catalogue from local compose** regardless of
   target.

None of these are capacity problems. **The system was never put under enough
load to find one** — the rate limiter refused 79% of traffic before anything
saturated.

---

## 7. Teardown

Every billable resource was destroyed immediately after this run. Verification
output is in `GOA-036-staging-teardown.md`.

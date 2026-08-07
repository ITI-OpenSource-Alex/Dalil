# GOA — Scope Reduction Plan for Final 7–10 Days

**Date:** 2026-07-29
**Basis:** `docs/dorgham-context/GOA_complete_documentation.md` (90-ticket plan, 4 sprints), `docs/dorgham-context/tickets/all_tickets.md` (43 open cards, 26 done), `GOA-058_remaining_work.md`, and a direct audit of `services/`, `apps/`, `infra/`.

---

## 0. Where the project actually is

**Done (26 cards):** monorepo + docker-compose, shared contracts, Gateway (Go/Fiber + JWT + auth refactor), User service (NestJS, refresh rotation, password reset, email verify), Orchestration scaffold + Supervisor, RAG service + **Profile Matcher 3-stage scoring** + UserUpdated snapshot, Speaking service + **4-agent swarm**, Writing scaffold + CV upload, Ingestion scaffold + 2 adapters, Next.js app + landing/onboarding/login/reset, Exam service scaffold + exam shell UI, Terraform 069/070/072.

**In progress (7):** GOA-074 (CI/CD OIDC), GOA-049 (Cambridge ingestion), GOA-050 (Reading engine), GOA-051 (Listening engine), GOA-071 (Terraform ECS), GOA-014 (Writing swarm), GOA-018 (Orchestration wiring).

**Blocked (4):** GOA-067, GOA-068, GOA-019, GOA-053.
**TODO (5):** GOA-052, GOA-087, GOA-020, GOA-086, GOA-088.

**Never started, still in the plan:** essentially all of GOA-021→047 (notification service — the directory is *literally empty*, scholarship matcher, CV review agent, observability dashboards, LLM-as-a-Judge CI, profile page, staging E2E, Lambda migration, speaking latency work, RAG re-ranking, security hardening, application checklist, load test, prod env, long-term memory, Stripe, Gold Tier docs, data freshness, polish tickets, regression suite, opportunity guide, cost monitoring, demo env) plus exam tickets GOA-056→066.

**The arithmetic:** ~45 unstarted items + 16 open cards versus 7–10 days. Historical velocity is ~10 commits/day across the team. Finishing the plan is not on the table. The only question is what gets cut, and cutting late is more expensive than cutting now.

**Two structural risks nobody has ticketed:**

1. **Merge debt.** Seven unmerged local branches, plus `origin/Rag/Ingestion`, `origin/Refactoring`, `origin/feat/GOA-019…`, `origin/GOA-076-Auth`. HEAD is on `fix/GOA-058-writing-exam-ui`, not `dev`. Integrating four+ weeks of parallel work in the final days is the single most likely way this project fails its demo. This must be Day 1.
2. **Dead scaffolding.** `services/notification/` is empty. `services/speech/` contains only `main.py` and duplicates the Speaking service's role. Both appear in `docker-compose.yml` and the architecture docs. An examiner who opens either directory finds nothing. Delete them or the architecture claim becomes a liability.

---

## 1. Features to remove entirely from the plan

Cut these now. Do not "keep them in case there's time" — an open scope item costs coordination overhead even when nobody works on it.

| # | Feature | Tickets | Why cut |
|---|---|---|---|
| 1 | **Listening exam** | GOA-051, GOA-056 | Highest effort-to-value ratio in the project. Needs Cambridge MP3s (licensing risk), S3 audio hosting + pre-signed URLs, an audio player with section progression, and section-timed state. The **grading logic is byte-identical to Reading** — it demonstrates nothing Reading doesn't already demonstrate. Zero AI content by design. Cut it and say in the report: "Listening reuses the Reading grading engine; not included in the MVP build." |
| 2 | **Speaking *exam mode*** (Part 1/2/3) | GOA-052, GOA-067, GOA-057 | Not to be confused with speaking *practice*, which is already built and stays. Exam mode adds server-enforced prep/speak timers, per-part transcript storage, a whole new holistic evaluation endpoint with an extended agent schema (`part_notes`, `examples`), and a 3-part UI with timers. That is a multi-day, three-service, WebSocket-timing feature with a wide bug surface, delivering a **worse demo** than the existing free-form speaking practice because it takes 11–14 minutes to run. |
| 3 | **Stripe / payment flow** | GOA-039 | Never demoed live (test mode only), never impresses an examiner, entirely orthogonal to the AI thesis of the project. Replace with a `tier` column on the user (already largely there) and a gate check. |
| 4 | **Notification service + scholarship matcher + SES** | GOA-023, GOA-024 | A whole unbuilt service (empty directory), a diff engine, an SQS consumer, and SES domain verification — for a feature whose entire demo is "an email arrives." Cannot be demonstrated live. Cut the service; keep the *event contract* in `packages/contracts` so the async architecture story remains true. |
| 5 | **Lambda migration** | GOA-031, GOA-072 runtime | Moving working ECS/container workloads to Lambda late is pure risk with no visible payoff. Terraform for it already exists — leave it as documented IaC, don't migrate. |
| 6 | **Production environment** (domain, SSL, WAF, CloudFront) | GOA-037 | One deployed environment is sufficient for a graduation demo. A second one doubles the deploy surface at the worst possible moment. |
| 7 | **Load / performance testing** | GOA-036, GOA-032 | 100 concurrent RAG users + 20 speaking sessions costs real money in tokens and multiple days of tuning. Nobody grades throughput on a graduation project. Report measured single-user P95 latencies instead — you get 80% of the credibility for 5% of the work. |
| 8 | **Long-term conversation memory** | GOA-038 | Redis 24h session memory (already built) is indistinguishable from long-term memory in a 10-minute demo. |
| 9 | **Weekly re-ingestion / data freshness** | GOA-041 | Scheduled EventBridge job that by definition cannot fire during a demo. |
| 10 | **Egyptian visa adapters (15 of them)** | GOA-086 | Fifteen separate scrapers against fifteen fragile embassy websites. Replace with a seeded `visa_requirements` JSON fixture for 2–3 countries. The RAG answer looks identical to the user; the scraping is invisible. |
| 11 | **Cost monitoring / AWS tagging** | GOA-046 | Langfuse already tracks per-call token cost. That is the interesting number. Cost Explorer alerts are ops hygiene, not project content. |
| 12 | **Question bank expansion (Cambridge 11–13)** | GOA-065 | The demo uses one test. 32 Reading passages versus 20 changes nothing. |
| 13 | **Exam observability + alarms** | GOA-066 | Metrics on a service you'll demo once. |
| 14 | **Opportunity guide / zero-token FAQ** | GOA-045 | Duplicates RAG Q&A with a second, worse code path. |
| 15 | **Exam history dashboard** | GOA-062 | Trend charts require multiple exam attempts to look non-empty. In a demo it shows one data point. |

---

## 2. Already-implemented features that can be dropped with minimal impact

These cost you *maintenance and integration risk*, not build time. Removing them makes the final integration smaller.

| Feature | Location | Recommendation |
|---|---|---|
| **`services/speech/`** | `services/speech/` — a stub `main.py` only | **Delete.** It overlaps the Speaking service and is dead weight in docker-compose and the architecture diagram. |
| **`services/notification/`** | Empty directory | **Delete** the directory and its compose entry. Keep the `NotificationRequested` event in `packages/contracts` so the SQS architecture claim stays honest. |
| **Speaking share links** (`/speaking/share/[token]`) | `services/frontend/app/speaking/share/` | Keep only if already working end-to-end. Public token-based sharing is a security surface (unauthenticated route) that adds nothing to the demo. If it needs any further work, delete the route. |
| **Academic Task 1 stimulus images** | Already deliberately removed per `StimulusPanel.tsx` header comment | **Confirm the removal is permanent** and update GOA-058's AC + the docs so it's a documented decision, not an open gap. Do not rebuild it — the writing pipeline no longer does image evaluation. |
| **Duplicated Section 12 in the master doc** | `GOA_complete_documentation.md` lines 825–960 duplicate lines 606–820 | Delete the duplicate. Examiners read the doc. |
| **`gBzYDiLL - the-last-dance (1).json`** (1.7 MB Trello export at repo root) | repo root | Move to `docs/` or delete. Repo-root junk reads as sloppiness. |
| **15 visa adapter implementation-plan files** | `docs/dorgham-context/implementation-plans/GOA-086/` | Move under an `archive/` or `deferred/` folder so the docs tree reflects actual scope. |

---

## 3. Features to simplify rather than fully implement

| Feature | Planned | Simplified version | Saving |
|---|---|---|---|
| **CV processor** (GOA-087) | S3 `ObjectCreated`-triggered Lambda, content-hash idempotency, `CVProcessed` SQS event, LocalStack notification wiring | **Synchronous extraction inside the Writing service** on upload: `pdfplumber`/`python-docx` → Haiku structured extraction → persist → return. Skip the Lambda, the S3 trigger, the idempotency hash, the SQS event. | ~2 days → ~4 hours. This is the highest-leverage simplification in the list: CV review is a core selling point and is currently blocked on infrastructure it doesn't need. |
| **Structured opportunity ingestion** (GOA-088) | 3 structured adapters (Mastersportal, DAAD, Chevening) + dual-write pipeline + content hashing + Prometheus | **Seed `program_requirements` and `scholarship_programs` from a curated JSON fixture** (~30 programs, hand-checked). Keep the upsert endpoints (they exist) so the ingestion *path* is real; skip the scrapers. | ~4 days → ~1 day. Data quality actually goes *up* — hand-curated beats a rushed scraper. |
| **LLM-as-a-Judge** (GOA-028) | Runs in CI on every PR, blocks merges, S3 report history, PR comment bot | **One offline script** run once at the end, producing `evals/reports/final.json` + a table in the report. | ~2 days → ~4 hours. You still get the Gold Tier evidence; you skip the CI plumbing. |
| **Evaluation suite** (GOA-020) | 50 golden Q&A + 20 profiles + 10 transcripts + 5 essays, regression detection, S3 upload, PR comments | **20 golden Q&A + 8 profiles + 3 transcripts + 3 essays**, run manually, results pasted into the report. | ~3 days → ~1 day. |
| **Observability** (GOA-027) | Langfuse + CloudWatch dashboards + alarm set | **Langfuse only** (already wired) + one Grafana/CloudWatch screenshot per service. Traces are what demonstrate agent orchestration; dashboards demonstrate ops. | ~2 days → ~half a day. |
| **Security hardening** (GOA-034) | Full OWASP LLM Top 10 across all services | **Three guardrails, tested and documented**: prompt-injection prefix defence in the Supervisor, PII redaction on outputs, per-user rate limit at the Gateway (already exists). Document the other seven as "identified, not implemented." | ~3 days → ~1 day. Honest gap documentation scores better than a half-built claim. |
| **E2E tests** (GOA-030, GOA-063) | 4 full journeys × Academic + General | **One Playwright happy path per demo pillar** (auth+onboarding, chat+matching, reading exam, writing exam). Four tests total. | ~3 days → ~1 day. |
| **Freemium enforcement** | Stripe + tier logic + upgrade UI | **Hardcoded `tier` on the user + Gateway gate check + a static "Upgrade" screen** that flips the flag. Demonstrates the gate; skips the payments integration. | ~2 days → ~2 hours. |
| **Notifications** | SES email + in-app alerts + diff engine | **In-app alert list seeded with 2–3 rows** rendered on the profile page. | ~3 days → ~2 hours. |
| **Cambridge content ingestion** (GOA-049) | Books 14–18, 20 Academic + 20 General Reading + 20 Listening | **1 Academic + 1 General Reading test, fully verified answer keys.** Listening dropped (see §1). | ~2 days → ~half a day. Verified keys matter far more than volume — GOA-064 grading accuracy is trivially satisfied with 2 tests. |
| **Under-minimum word warning** (GOA-058 §2.1) | — | Parameterise the string by task number. It currently tells Task 2 candidates a factually false thing. **1–2 hours, do it** — it's a visible content bug in a feature you *will* demo. |

---

## 4. Services, workflows, APIs, infra and screens to merge

**Services: 11 directories → 7 real ones.**

- Delete `services/speech/` (dead, overlaps Speaking).
- Delete `services/notification/` (empty).
- **Merge the CV processor into the Writing service** rather than a separate Lambda (see §3).
- **Do not split Exam and Writing evaluation paths.** GOA-068 adds `POST /essays/evaluate/exam` as a *third* prompt variant alongside the standard writing evaluation. Collapse to **one endpoint with an `exam_mode: bool` flag** and one prompt set. Two prompt families for one agent swarm is duplicated prompt-tuning effort and duplicated failure modes.
- Likewise, **do not build Speaking `POST /evaluate/holistic`** (GOA-067) as a second evaluation path — it dies with the speaking exam cut.

**Frontend screens: consolidate.**

Current routes: `/`, `/login`, `/register`, `/reset-password`, `/onboarding`, `/chat`, `/profile`, `/speaking`, `/speaking/history`, `/speaking/history/[id]`, `/speaking/share/[token]`, `/exam`, `/exam/shell`, `/exam/results`.

- **Merge `/profile` and the exam history dashboard** (GOA-062) into one page: profile fields + CV status + opportunity matches + a flat list of past attempts. One page, no charts.
- **Merge the application checklist** (GOA-035) into the profile's match detail view as a static list derived from the existing gap report — the gap report already computes exactly this. Do not build a separate feature.
- **Drop `/speaking/share/[token]`** unless it's already finished and tested.
- **Result:** ~9 screens instead of ~14.

**Infrastructure: one environment, one deploy path.**

- Terraform 069/070/072 are done; 071 (ECS) is in progress. **Timebox ECS to 2 days.** If it isn't green by end of Day 4, fall back to **docker-compose on a single EC2 instance** using the images you already build. The Gold Tier claim is "IaC exists and the system is deployed" — that survives the fallback, and the fallback is a known-good path since compose already works locally.
- Drop the separate prod environment (§1). Rename staging to "the deployed environment" in the docs.
- Keep GOA-074 (OIDC + branch protection) — it's nearly done and cheap.

**APIs:** RAG currently exposes `documents`, `query`, `scoring`, `visa`, `program_requirements`, `scholarship_programs`. If the visa adapters are cut (§1), `visa.py` serves seeded data only — keep the endpoint, delete the adapter plumbing behind it.

---

## 5. Biggest remaining time sinks — keep or kill

| Task | Est. effort | Verdict | Reasoning |
|---|---|---|---|
| **GOA-018 — Orchestration wiring** | 2–3 days | **KEEP — top priority** | This is the spine. Without it the Supervisor doesn't route to Writing/Speaking/RAG and the "hierarchical multi-agent orchestration" claim — the single biggest Gold Tier item — is unprovable. Everything else is negotiable; this is not. |
| **GOA-014 — Writing swarm** | 1–2 days remaining | **KEEP** | In progress, 4 agents, marquee AI feature, blocks GOA-053/068 and the whole writing exam demo. |
| **GOA-021/071 — AWS deploy** | 3–5 days, high variance | **KEEP, timeboxed to 2 days with an EC2 fallback** | Highest-variance item on the board. Terraform/ECS debugging is unbounded. The fallback is what protects the deadline. |
| **GOA-051 + GOA-056 — Listening** | 3–4 days | **KILL** | See §1. Best single cut available. |
| **GOA-052 + 067 + 057 — Speaking exam** | 4–5 days across 3 services | **KILL** | See §1. Second-best cut. Speaking practice already demos the same agents. |
| **GOA-087 — CV processor** | 2–3 days as specified | **KEEP, simplified to ~4 hours** | CV review is in the project's one-line pitch. The *Lambda* is what's expensive, not the extraction. |
| **GOA-050 + 049 — Reading exam** | ~1.5 days remaining | **KEEP** | Nearly done, zero token cost, deterministic, no AI-flakiness risk. A reliable demo segment is worth a lot at this stage. |
| **GOA-053 + 068 — Writing exam mode** | 2 days | **KEEP, merged** | Collapse to one evaluation endpoint (§4). The frontend (GOA-058) is largely done per the audit. |
| **GOA-019 — Chat UI (SSE, CV upload, speaking)** | 2 days | **KEEP** | It's the front door of the demo. Blocked on GOA-018, so it's the immediate follow-on. |
| **GOA-086 + 088 — Ingestion adapters** | 6–8 days combined | **KILL / seed instead** | Scrapers against 18 external sites, days from the deadline, is the highest bug-risk work remaining and is completely invisible in the demo. |
| **GOA-020 + 028 — Evals** | 5 days combined | **KEEP, simplified to ~1.5 days** | Gold Tier requires the evidence. It does not require CI integration. |
| **Branch integration** | 1–2 days, unticketed | **KEEP — Day 1** | Eight-plus divergent branches. If this is left until Day 8 it will consume Days 8–10. |

---

## 6. Recommended final scope (7–10 days)

**Three demo pillars. Nothing else.**

**Pillar 1 — Onboarding & Profile.** Register → verify → onboarding wizard → CV upload → synchronous extraction → profile page with structured CV fields. *(Mostly done; needs simplified GOA-087.)*

**Pillar 2 — AI Chat & Opportunity Matching.** Supervisor routes intents → RAG Q&A with citations over seeded data → Profile Matcher 3-stage scoring with confidence score + gap report → matches on the profile page with an inline checklist. *(Needs GOA-018, GOA-019, seeded data.)*

**Pillar 3 — IELTS Exam Prep (Reading + Writing) & Speaking Practice.** Reading exam with deterministic grading and band conversion → Writing exam Task 1/2 with the 4-agent swarm and weighted band → standalone Speaking practice with the 4-agent swarm. *(Needs GOA-050, GOA-049-lite, GOA-014, GOA-053 merged.)*

**Cross-cutting, kept:** Langfuse traces on every LLM call · JWT auth via httpOnly cookies · database-per-service (unchanged) · one SQS event flow (`UserUpdated` → RAG snapshot, already working) · one deployed environment · Terraform IaC in the repo · 4 Playwright happy paths · one eval report.

### Day-by-day

| Days | Work |
|---|---|
| **1** | **Freeze scope.** Merge all branches into `dev`, green the build. Delete `services/speech/`, `services/notification/`, dead compose entries. Archive cut tickets on Trello so the board reflects reality. |
| **2–3** | GOA-018 orchestration wiring (the critical path — put your strongest dev here). In parallel: GOA-014 writing swarm finish; GOA-050/049-lite Reading. |
| **3–4** | GOA-019 chat UI. Simplified GOA-087 CV extraction. GOA-053 writing exam via the merged endpoint. Seed the fixture data (30 programs, 3 visa countries, 2 Reading tests). |
| **4–5** | **Deploy.** ECS timebox ends end of Day 4 — decide ECS or EC2-compose and commit. Smoke-test everything against the deployed URL. |
| **6–7** | Bug fixing against the deployed environment only. GOA-058 word-warning fix. Security guardrails (3 of them). Profile page consolidation. |
| **7–8** | 4 Playwright happy paths. Eval script run → `evals/reports/final.json`. Langfuse screenshots. |
| **8–9** | Gold Tier self-assessment doc (honest: what's built, what's designed-not-built, and why). Architecture diagrams. README. Demo script. |
| **9–10** | **Buffer + two full demo rehearsals against the deployed URL.** No new code after Day 9. |

The buffer is not optional. Every schedule in this plan has been optimistic so far; this one should not repeat that.

---

## 7. Prioritised decision list

### MUST STAY — cutting these damages the project
1. Branch integration and a green `dev` build *(Day 1)*
2. GOA-018 — Orchestration / Supervisor routing
3. GOA-014 — Writing 4-agent swarm
4. Profile Matcher 3-stage scoring *(done — protect it, don't refactor)*
5. Speaking 4-agent swarm + speaking practice UI *(done — protect it)*
6. GOA-019 — Chat UI with SSE streaming
7. GOA-050/049-lite — Reading exam
8. GOA-053 — Writing exam mode (single merged endpoint)
9. One deployed environment (ECS **or** EC2-compose)
10. Langfuse tracing on every LLM call
11. Gold Tier self-assessment + demo script *(Days 8–9)*

### SIMPLIFY — keep the capability, drop the engineering
12. GOA-087 CV processor → synchronous, in-service, no Lambda
13. GOA-088 structured ingestion → seeded JSON fixture
14. GOA-020 + GOA-028 evals → offline script, smaller dataset, no CI gate
15. GOA-034 security → 3 guardrails implemented, 7 documented as gaps
16. GOA-027 observability → Langfuse + screenshots, no dashboards or alarms
17. E2E → 4 happy paths
18. Freemium → tier flag + gate check, no Stripe
19. Notifications → seeded in-app list
20. Profile / exam history / application checklist → one consolidated page
21. GOA-058 word-count warning → parameterise by task (1–2 hrs)

### CUT TODAY — remove from the board before anyone starts
22. GOA-051 + GOA-056 — Listening exam
23. GOA-052 + GOA-067 + GOA-057 — Speaking exam mode
24. GOA-086 — 15 Egyptian visa adapters
25. GOA-039 — Stripe
26. GOA-023 + GOA-024 — Notification service + scholarship matcher
27. GOA-031 — Lambda migration
28. GOA-037 — Production environment
29. GOA-036 + GOA-032 — Load testing and latency optimisation
30. GOA-038 — Long-term memory
31. GOA-041 — Data freshness
32. GOA-045 — Opportunity guide
33. GOA-046 — Cost monitoring
34. GOA-062 — Exam history dashboard
35. GOA-065 — Question bank expansion
36. GOA-066 — Exam observability
37. `services/speech/` and `services/notification/` directories
38. Academic Task 1 stimulus images *(confirm as a documented decision)*

---

## 8. Two notes on how this gets graded

**Document what you cut, and why.** A graduation project that says "we designed 90 tickets, scoped 40 for the MVP, and here is the reasoning" reads as engineering judgment. One that silently ships 40 of 90 reads as failure to deliver. Put §1 of this document, condensed, into the final report as a "Scope Management" section. The Listening cut in particular has a genuinely good justification — identical grading engine to Reading, zero AI content — and stating it is stronger than hiding it.

**Protect what already works.** Profile Matcher, the Speaking swarm, auth, and onboarding are done and working. The most common way projects fail in the last week is refactoring something that already worked. After Day 1, changes to those subsystems should require a specific bug as justification.

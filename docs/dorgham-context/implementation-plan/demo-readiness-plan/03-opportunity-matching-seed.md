# 03 — Opportunity Matching Seed Data

## Objective

Seed the RAG service's `local_user_profiles` table and expand the
`program_requirements` table so that "find me Master's programs" queries in
`/chat` return real, varied results instead of erroring.

## Background

"Find me Master's programs in Germany" is the product's headline promise and
the **only** entry point into the Application Checklist feature (the
flagship free feature). Today, this query fails.

Root cause, traced end to end:

- Chat routes an `OPPORTUNITY_SEARCH` intent to RAG's `POST /match`.
- `match_programs(user_id)` in `services/rag/app/services/scoring.py` calls
  `get_local_user_profile(user_id)`, which queries
  `local_user_profiles WHERE user_id = $1` — a **UUID column**.
- If no profile row exists for that user, `match_programs` raises
  `HTTPException(status_code=425, detail="Profile not yet replicated. Please retry.")`.
- `local_user_profiles` is populated **exclusively** by an SQS consumer
  (`app/services/sqs_consumer.py`, calling `upsert_local_profiles`) reacting
  to `UserUpdated` events published by the user service.
- The user service exposes no profile-update endpoint at all — only
  `POST /`, `GET /internal`, `GET /:id`, `GET /:id/subscription` — so there
  is currently **no in-product path** that could ever create this row for a
  real user, demo or otherwise.
- Separately, only 3 programs exist in `program_requirements`
  (`008_update_program_requirements.sql`: TU Munich, ETH Zurich, Erasmus
  Mundus) — thin for a feature described as scoring the European catalogue.

Without a seed, two of the demo's eight screens (opportunity matching and,
downstream, the checklist it feeds) are dead.

## Why This Matters

Opportunity matching is the bridge between the chat Q&A demo beat and the
Application Checklist demo beat — losing it doesn't just remove one screen,
it breaks the narrative connecting two others. It is also the flow most
directly tied to the product's stated value proposition, so a live error
here is the most damaging possible failure in front of a reviewer.

## Scope

**In scope:**
- One seeded `local_user_profiles` row for the demo account.
- 8–10 additional seeded rows in `program_requirements`, spanning multiple
  countries and a deliberate spread of eligibility thresholds.
- A documented runbook step for copying the demo account's real UUID into
  the seed after registration (see Edge Cases).
- Documenting the Redis cache key that must be flushed after seeding.

**Out of scope:**
- Building a real profile-sync endpoint or fixing the underlying
  `UserUpdated`/SQS replication path — that is real cross-service work,
  not demo-prep. The seed is a deliberate, documented workaround.
- Building the Opportunity/Program Detail Modal (spec item — not on the
  current demo path).
- Modifying `scoring.py`'s matching or gating logic.

## Files Expected to Change

```
services/rag/app/migrations/028_seed_demo_user_profile.sql        (new)
services/rag/app/migrations/029_seed_demo_programs.sql            (new)
docs/dorgham-context/DEMO_RUNBOOK.md                               (new or appended)
```

## Detailed Implementation Plan

**Seed A — the demo user's local profile.** Insert one row into
`local_user_profiles` with the demo account's UUID and: `gpa` 3.45,
`gpa_scale` 4.0, `ielts_score` 6.5, `ects` 180, `degree_level` `'Bachelor'`,
`work_exp` 1, `target_countries` `{Germany,Switzerland,Netherlands}`,
`field_of_study` `'Computer Science'`. Use exactly the columns
`get_local_user_profile` selects (`user_id`, `ects`, `gpa`, `gpa_scale`,
`ielts_score`, `degree_level`, `work_exp`, `extracurriculars`,
`target_countries`, `field_of_study`) — do not invent or omit fields.

The UUID problem: the demo account doesn't exist (and therefore has no
UUID) until it is registered through the actual product, which happens
after this migration is authored. Two approaches were considered:

- *Fixed UUID*: pre-create the user directly in the user service's database
  with a known UUID. Rejected — this couples two independent service
  databases and is brittle if the user service's schema or creation path
  changes.
- **Runbook step (recommended)**: ship the migration with a clearly-marked
  placeholder UUID (e.g., all zeros or a comment marker), and document a
  single `psql` `UPDATE` command in the demo runbook that sets the real UUID
  after the demo account is registered. This is one command, run once, on
  demo-prep day, and keeps the two services' seed data properly decoupled.

**Seed B — additional programs.** Add 8–10 rows to `program_requirements`
across Germany, Netherlands, Sweden, Italy, and Canada. Tune the values
deliberately rather than arbitrarily — this is what turns a seed into a
demo asset rather than just filler data:

- 3–4 programs the demo profile clears comfortably on every hard gate →
  high-confidence ("green") cards.
- 2–3 that land in a mid-range score → amber cards, demonstrating the score
  is actually computed rather than cosmetic.
- **At least one program that fails a hard gate** (ECTS or IELTS threshold)
  against the seeded demo profile. A blocked card reading something like
  "your ECTS credits (180) are below the minimum required (210)" is a
  *stronger* demo moment than three uniformly green cards, because it
  proves the eligibility engine is real. **Before relying on this**, verify
  how `scoring.py` actually surfaces blocked programs in the `/match`
  response — if the current implementation filters ineligible programs out
  entirely rather than returning them with a block reason, drop this
  sub-goal rather than modifying scoring logic under demo time pressure.

Populate `program_name`, `university`, `country`, `deadline` (all within the
next 6 months, so cards look live and current), `discipline` (must match
whatever `discipline_for_field_of_study('Computer Science')` returns, or be
left `NULL` — the matching query is explicitly null-tolerant by design), and
the four gate columns (`min_ects`, `min_gpa`, `min_ielts`,
`min_work_experience`).

**Runbook.** Create (or append to) `DEMO_RUNBOOK.md` with: register demo
account → copy its UUID into the RAG database per the command above → warm
the checklist cache for the demo program (see the Phase 2 caching task) →
clear stale `sessionStorage` state → verify each of the eight demo screens
in sequence. This runbook is itself a deliverable — it's what makes the
demo repeatable rather than a one-off that happened to work once.

**Cache flush.** `match_programs` caches its result in Redis under
`match:{user_id}`. After seeding the profile row, that key must be flushed
(or was never populated) — otherwise the first `/match` call's 425 error
gets cached and the demo continues to fail even after the seed is correct.
Document this explicitly in the runbook; it is the kind of gap that costs
someone 30 confused minutes if undocumented.

## Edge Cases

- If the demo account is re-registered (e.g., a fresh account per rehearsal
  run, per the standing recommendation to keep the Reading-exam demo
  account single-use), the UUID copy step must be repeated for **that**
  account, or matching will 425 again. Make this explicit in the runbook
  rather than assuming a single static demo account.
- The matching query is null-tolerant on `target_countries` and
  `field_of_study` — an absent preference widens the search rather than
  emptying it. Do not add validation logic assuming otherwise.
- `MATCH_CANDIDATE_CAP` bounds the candidate query; with only ~13 total
  seeded programs this is a non-issue, but don't assume it scales past that
  cap without checking its value if more programs are added later.

## Acceptance Criteria

- `POST /api/chat` with an opportunity-search message returns a
  `match_results` event containing at least 5 programs.
- Returned programs span at least three distinct confidence bands
  (high / mid / low).
- Every returned program has a non-null `programId` that the checklist
  endpoint (`GET /api/checklists/:programId`) accepts without error.
- The runbook explicitly documents the Redis key that must be flushed after
  seeding.

## Verification Steps

1. Apply both migrations against the running Postgres instance.
2. Register the demo account through the actual product UI; copy its UUID
   into `local_user_profiles` per the runbook command.
3. Flush (or confirm absence of) the `match:{user_id}` key on the RAG
   Redis instance.
4. In `/chat`, send "Find me Master's programs in Germany."
5. Confirm opportunity cards render with varied match percentages, real
   university names, and future-dated deadlines.
6. Click "Get Checklist" on one card; confirm it navigates to a working
   checklist page for that program.

## Dependencies

Should be sequenced **after** [04 — Real User Identity Wiring](04-real-user-identity.md)
is implemented, because this seed is only verifiable end-to-end once chat
actually sends the demo account's real UUID as `userId` instead of the
hardcoded placeholder. The seed migrations themselves can be authored
independently, but full verification requires 04 to be in place.

## Estimated Effort

45 minutes.

## Risk

**Low.** A single additive `INSERT` into a table nothing else writes to
during the demo. Does not alter any application code. The only real care
point is correctly matching the demo user's real UUID after registration.

## Status

Completed. `services/rag/app/migrations/028_seed_demo_user_profile.sql` and
`029_seed_demo_programs.sql` implemented and verified live end-to-end
through the real Gateway with a real authenticated session: a
`"Find me Masters programs in Germany"` chat message returned 8 ranked
programs (score range 63.46–69.92) plus 1 correctly blocked program
(`Requires 210 ECTS`), and `GET /api/checklists/:programId` accepted one of
the returned program IDs and returned a real checklist. Two deviations
from the plan's literal instructions were required and are fully
documented in `docs/dorgham-context/DEMO_RUNBOOK.md`: (1) the profile's
`degree_level` uses `'Master'` instead of the literal `'Bachelor'` — the
literal value would hard-gate-block every program in the catalog, verified
against `gates.py`'s exact-equality check; (2) the seed conflicts on
`source_url`, not `(university, degree_level, country)` as the plan
assumed — that constraint was replaced by
`020_program_source_url_identity.sql`, discovered when the first version
of the migration crashed the RAG service on startup. Also documented: the
platform's literal "green ≥ 80%" card-color threshold is mathematically
unreachable with this exact profile (verified with a calculator replicating
`compute_soft_score`; ceiling ≈ 76.5% even at maximum plausible inputs) —
the 8 returned programs instead span the highest realistically achievable
relative spread, plus a genuinely blocked card.

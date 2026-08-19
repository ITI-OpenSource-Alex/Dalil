# Demo Runbook

Operational notes for running the live demo. Each section is added by the
implementation-plan document that made it necessary — see
`docs/dorgham-context/implementation-plan/demo-readiness-plan/` for the
full plan.

## Reading Exam Data (doc 01)

**What was done:** `services/exam/app/migrations/008_seed_demo_reading_test.sql`
seeds one complete, gradable Reading test (`book_ref = 'GOA-DEMO'`,
`test_number = 1`, `exam_type = 'academic'`) directly into the `questions`
table — 15 questions across all 5 Cambridge question-type renderers (5 per
Section 1/2/3), with a matching, fully server-gradable `answer_key`.

**Route taken:** Route B (hand-authored SQL seed), per the implementation
plan. Route A (running the existing OCR ingestion pipeline against the former
repo-root Trello export, since removed during repository cleanup) was attempted
first and abandoned immediately — that file was a **Trello board export** (top-level
keys: `id, name, desc, cards, checklists, customFields, labels, lists,
members, actions`), not Cambridge OCR text, and is not a valid input to
`ReadingParser.parse_text`. No CLI ingestion script was written, per the
plan's "only attempt Route A if it's fast" guidance.

**How it's applied:** `services/exam/app/core/database.py`'s
`run_migrations()` runs every `*.sql` file under `app/migrations/` in
filename order on service startup, tracked in a `migrations_log` table so
each file only runs once. No manual step is required beyond starting (or
restarting) the exam service — `docker compose up` (or `restart exam` if
the container was already running when the migration file was added) is
sufficient. Verified live: the migration executed successfully against the
running stack and a full create → answer → submit → grade cycle succeeded
twice, from two different fresh (randomly generated) user accounts.

**⚠️ Pre-existing question bank in this environment.** The Postgres data
volume already used in this environment (`goa_pgdata`) was **not empty** —
it already contained real, previously-ingested Cambridge IELTS Reading
questions (`IELTS-14` through `IELTS-19`, several test numbers each) from
some earlier session's ingestion run, independent of this seed migration
and not tracked by any file in `app/migrations/`. Of that pre-existing
data, **4 tests were already fully scorable** (question count exactly
matches answer-key count, the condition `QuestionRepository`'s
`_SCORABLE_CLAUSE` requires): `IELTS-15/4`, `IELTS-16/4`, `IELTS-17/3`,
`IELTS-17/4` (all `exam_type = academic`). This means, in this specific
environment, the zero-question-data blocker the implementation plan
identified from the migrations directory alone was **less severe at
runtime than a fresh environment would show** — but this is environment
state, not something guaranteed to exist elsewhere (a teammate's machine,
CI, or a genuinely fresh `docker compose down -v` reset will not have it).
**Do not rely on this pre-existing data for the actual demo** — it is
undocumented, was not produced by this task, and its origin/completeness is
unverified. The seed migration in this task is what guarantees a servable
Reading test regardless of environment history; treat the pre-existing
tests as an unplanned bonus, not a dependency.

**Known limitation — per-attempt test selection is random, not targeted.**
`SessionService.create_session` (used by the frontend's "Take Exam" button,
via `POST /api/exam/sessions`) calls
`QuestionRepository.get_random_question`, which picks **uniformly at
random** among *all* scorable Reading/academic tests currently in the
database — it does not prefer the seeded `GOA-DEMO` test. In this
environment that pool currently has 5 members (4 pre-existing + `GOA-DEMO`),
so a "Take Exam" click has roughly a 1-in-5 chance of landing on the
seeded, demo-verified content on the first try. If a different (real
Cambridge) test is drawn instead, that is still a fully real, working
Reading exam — the acceptance criteria for this task do not require the
*specific* seeded test to be shown, only that a servable one exists — but
if the demo script specifically wants the seeded 15-question test (shorter,
deliberately tuned for an uneven weak-type score), the presenter should
either: (a) accept whichever test is drawn (all are real and working), or
(b) draw and discard sessions with a disposable test account shortly before
presenting until `GOA-DEMO` comes up, then use that same account live. Do
not attempt to remove the pre-existing tests to force selection — they are
undocumented pre-existing state, not something this task owns.

**Known limitation — band score ceiling on the seeded test.** The seeded
test has 15 questions, not the full 40 a real IELTS Reading paper has.
`GradingService.grade_reading` looks up `raw_score` directly against a
band-conversion table calibrated for a 40-question paper — it does **not**
normalize by the number of questions actually asked. A **perfect 15/15** on
the seeded test therefore returns `band_score = 5.0`, not a high band —
verified live. This does not affect the acceptance criteria (a real
`raw_score`/`band_score`/`per_question_result`/`section_breakdown` are
still returned and rendered correctly), but the presenter should not
narrate a perfect run as "band 9" — say "raw score 15 out of 15" instead,
or deliberately miss one or two questions so the displayed band number
doesn't read as suspiciously low for a flawless run.

**Do not run the Reading demo twice from the same account.**
`get_random_question`'s query excludes any question a given `user_id`
already has *any* session against (not just completed ones) via a
`LEFT JOIN ... AND s.id IS NULL` — every test in the pool is a one-shot
per account. A second "Take Exam" click from the same logged-in account
will keep drawing from the shrinking remaining pool and will eventually
404 once every scorable test has been drawn by that account. **Always use
a fresh account for each live Reading-exam run** (including rehearsals —
rehearsing from the same account you intend to demo with will burn through
the pool before you're on stage).

**Suggested demo answers for the seeded `GOA-DEMO` test**, chosen to
produce a deliberately uneven, non-trivial question-type breakdown (see
`services/exam/app/migrations/008_seed_demo_reading_test.sql` for the full
question text and correct answers):

| Q# | Type | Suggested live answer | Correct? |
|----|------|------------------------|----------|
| 1 | Multiple Choice | B | ✅ |
| 2 | Multiple Choice | C | ✅ |
| 3 | True/False/Not Given | TRUE | ✅ |
| 4 | True/False/Not Given | TRUE | ❌ (correct: FALSE) |
| 5 | Short Answer | London | ✅ |
| 14 | Sentence Completion | one | ✅ |
| 15 | Sentence Completion | bleaching | ✅ |
| 16 | Matching Information | C | ✅ |
| 17 | Matching Information | (leave blank or guess wrong) | ❌ (correct: B) |
| 18 | True/False/Not Given | TRUE | ❌ (correct: FALSE) |
| 27 | Short Answer | Austria | ✅ |
| 28 | Short Answer | 2023 | ✅ |
| 29 | Multiple Choice | B | ✅ |
| 30 | Sentence Completion | two | ✅ |
| 31 | Matching Information | B | ✅ |

This produces True/False/Not Given at 1/3 correct (33%) — a clear, honest
"weakest question type" for the results page's type-breakdown panel to
surface, without needing to fake anything.

## Opportunity Matching Seed Data (doc 03)

**What was done:**
`services/rag/app/migrations/028_seed_demo_user_profile.sql` seeds one
`local_user_profiles` row for the demo account (GPA 3.45/4.0, IELTS 6.5,
180 ECTS, 1 year work experience, extracurriculars 8/10, target countries
Germany/Switzerland/Netherlands, field of study Computer Science).
`services/rag/app/migrations/029_seed_demo_programs.sql` adds 9 programs to
`program_requirements` across Germany, the Netherlands, Sweden, Italy and
Canada, tuned against that exact profile.

**Required manual step — set the real demo account UUID.** Both migrations
ship with a placeholder identity (`local_user_profiles.user_id =
'00000000-0000-0000-0000-000000000000'`) because the demo account does not
exist until it is registered through the actual product. After registering
the demo account, run:

```sql
UPDATE local_user_profiles
SET user_id = '<the demo account''s real UUID from GET /api/profile>'
WHERE user_id = '00000000-0000-0000-0000-000000000000';
```

**Repeat this step for every new demo account** — including rehearsal runs
using a different account than the final live one, and including any
re-registration of the same demo account (its UUID changes each time).

**Required manual step — flush the match cache.** `match_programs()`
caches its full response in Redis under `match:{user_id}` for 1 hour
(`services/rag/app/services/scoring.py`, `CACHE_TTL = 3600`). If `/match`
was ever called for this user_id *before* the profile row existed (e.g.
during testing, or a demo dry-run before the UUID was updated), that
failure is **not** cached — `match_programs` only caches successful
responses — but a stale *successful* response from a previous seed/profile
version would be. After updating the UUID above, flush the key:

```sh
docker compose exec redis-cache redis-cli -n 2 DEL "match:<the real UUID>"
```

**Verified live, twice:** the target Redis instance/DB index is
**`redis-cache`, logical DB `2`** — confirmed directly from
`docker-compose.yml`'s `rag` service (`REDIS_URL=redis://redis-cache:6379/2`).
Flushing the wrong DB index (e.g. DB `1`, used by a different service) is a
silent no-op — `redis-cli -n 1 DEL ...` will return `0` whether or not a
stale key exists on DB `2`, which cost real time confirming during this
task's own verification. Double-check the DB index against
`docker-compose.yml` if this ever changes.

**⚠️ Schema mismatch discovered — `program_requirements`'s unique
constraint moved.** The implementation plan (and
`014_add_program_requirements_upsert_support.sql`, an earlier migration)
assumed idempotency was keyed on `(university, degree_level, country)`.
`020_program_source_url_identity.sql` later **dropped that constraint and
re-keyed the table's unique identity to `source_url` instead**
(`uq_program_requirements_source_url`). The first version of migration 029
used `ON CONFLICT (university, degree_level, country)` per the plan's
literal wording and **failed the RAG service's startup outright**
(`asyncpg.exceptions.InvalidColumnReferenceError: there is no unique or
exclusion constraint matching the ON CONFLICT specification`), confirmed
directly against the running container's logs and against `\d
program_requirements` in `psql`. Fixed by giving every new row a distinct
`source_url` (`https://goa.internal/seed/demo-program/<slug>`, following
the same internal-namespace convention `020`'s own backfill used) and
conflicting on that column instead. If any *future* migration touches
`program_requirements`'s upsert/idempotency behavior again, verify the live
constraint with `\d program_requirements` before assuming any older
migration file's description of it is still accurate — this table's unique
key has already changed once.

**⚠️ Deviation from the plan's literal profile value — `degree_level`.**
The implementation plan specifies `degree_level: 'Bachelor'` for the seeded
profile. This was **not implemented literally** — verified against
`services/rag/app/services/gates.py`'s `check_hard_gates`, `degree_level`
is an **exact-equality** hard gate (`profile.degreeLevel !=
program.degree_level` → blocked), not a "meets or exceeds" comparison.
With `degree_level = 'Bachelor'` on the profile, **every** `'Master'`
program in the catalog — including the three pre-existing seed programs
(`TU Munich`, `ETH Zurich`, `Erasmus Mundus`) this same profile is meant to
match against — would hard-gate-block outright with zero non-blocked
results, directly violating this same document's acceptance criterion of
returning programs across multiple confidence bands. `degree_level =
'Master'` is used instead, for both the profile and every one of the 9 new
program rows, matching the demo's own "find me Master's programs" premise
and the three pre-existing programs. Verified live: with this value, 7 of
8 in-country candidates return varied, non-zero scores and the 9th
(deliberately) hard-gate-blocks on ECTS as intended — see below.

**⚠️ Finding — the platform's literal "green ≥ 80%" card-color band is
mathematically unreachable with this exact profile.** Before finalizing
program values, a standalone calculator script replicating
`compute_soft_score` exactly (`services/rag/app/services/soft_score.py`)
was used to check the achievable score range. With this profile's fixed
inputs (GPA 3.45/4.0 → 86.25%, IELTS 6.5/9 → 72.2%, work experience 1 year,
extracurriculars 8/10), `candidate_strength` computes to **66.94%**, which
is weighted at 65% of the final score (`PROGRAM_FIT_WEIGHT = 0.35`).
Even an artificially generous program (near-zero requirements on every
dimension) only pushes `program_fit` to its practical ceiling of
**~86.7%**, giving a theoretical maximum total score of **~73.9%** — never
80%. Raising `extracurriculars` to its maximum (10/10, not used — 8 was
kept as a more realistic value) only raises the ceiling to **~76.5%**,
still short of 80. **This is a structural property of the scoring
formula's weight split, not a seed-tuning failure**, and closing it would
require either changing the profile's GPA/IELTS (fixed by the
implementation plan's literal Seed A values) or changing
`compute_soft_score`'s weights (explicitly out of scope: "Modifying
`scoring.py`'s matching or gating logic" is listed as Out of Scope in the
implementation plan). The 9 seeded programs are tuned to produce the
**highest realistically achievable relative spread** instead — verified
live via a real `/api/chat` call through the Gateway with a real
authenticated session:

| University | Score | Tier |
|---|---|---|
| Technical University of Berlin | 69.92 | Highest |
| Vrije Universiteit Amsterdam | 69.58 | Highest |
| RWTH Aachen University | 68.67 | Highest |
| University of Twente | 67.58 | Highest |
| Technical University Munich *(pre-existing)* | 66.75 | Mid |
| ETH Zurich *(pre-existing)* | 64.56 | Mid |
| Delft University of Technology | 63.46 | Mid |
| University of Stuttgart | 0.0 (blocked — `Requires 210 ECTS`) | Blocked |

This satisfies the acceptance criterion's *substance* — real, distinct,
computed confidence levels rather than uniform or fabricated numbers, plus
a genuinely blocked card with a real reason — but **does not** produce a
card that renders in the platform's literal green (≥80%) color band. If a
future presenter specifically wants a green card, the only paths are: (a)
seed a second profile with stronger GPA/IELTS values for that specific
purpose, or (b) revisit `compute_soft_score`'s weighting — both out of
scope for this task.

**⚠️ Country-filter interaction — 3 of the 9 new programs never appear for
the demo account.** `match_programs()`'s candidate query filters by exact
membership in the profile's `target_countries` *before* scoring runs
(`country = ANY($1::text[])`). The demo profile's `target_countries` is
`{Germany, Switzerland, Netherlands}` (per the implementation plan's Seed
A). The implementation plan's Seed B separately instructs seeding programs
"across Germany, Netherlands, Sweden, Italy, and Canada." Both instructions
were followed literally, but the consequence — verified live — is that
**KTH (Sweden), Politecnico di Milano (Italy), and University of Toronto
(Canada) will never appear in a `/match` response for the demo account**;
they exist in the catalog (supporting the "we score the European
catalogue" narrative and available if the demo profile's target countries
are ever widened) but are functionally inert for the actual demo run. The
8-program table above is the complete, verified set of what the demo
account actually sees.

**Verified live, full path:** registered a real account through the
product, logged in, pointed the seeded profile at its real UUID, flushed
the cache, then sent `"Find me Masters programs in Germany"` through the
real `POST /api/chat` endpoint (through the Gateway, with the account's
real auth cookie — not a direct internal-API-key call). The response
matched the table above exactly. `GET /api/checklists/:programId` was then
called with one of the returned `programId`s and returned `200` with a
real, generated checklist.

## Cache and Environment Notes

- **RAG match cache**: `match:{user_id}` on `redis-cache` DB `2`, TTL 1
  hour. Flush after any change to a user's seeded/replicated profile — see
  "Opportunity Matching Seed Data" above.
- **Exam service and RAG service both auto-run pending migrations on
  startup** (`services/exam/app/core/database.py`,
  `services/rag/app/core/database.py`), tracked in a `migrations_log`
  table so each file only runs once. If a new migration file is added
  while its service's container is already running, **restart that
  container** (`docker compose restart <service>`) to pick it up —
  migrations do not apply retroactively to an already-running process.
- **The `orchestration` service is required for any chat-routed flow**
  (Q&A, opportunity search, writing, speaking-via-chat) — it is not always
  running by default in every dev environment snapshot; confirm with
  `docker compose ps` and `docker compose up -d orchestration` if a chat
  request returns `502 {"error":"failed to contact orchestration service"}`.

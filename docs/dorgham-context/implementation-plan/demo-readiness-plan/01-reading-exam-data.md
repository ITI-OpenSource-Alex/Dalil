# 01 — Reading Exam Question Data

## Objective

Guarantee that at least one complete, well-formed Reading exam test exists in
the `questions` table so that the Reading exam — the strongest asset in the
entire application — can actually be started, completed, and graded during
the demo.

## Background

The Reading exam UI is production-grade: a 272-line reducer-driven component
(`ReadingExam.tsx`) with a split scrollable passage/question panel, five
Cambridge question-type renderers (Multiple Choice, Matching, True/False/Not
Given, Fill-in-the-Blank, Short Answer), a question navigation sidebar,
passage highlighting, an unanswered-count submit modal, and a results view
with section breakdowns and per-question-type analysis. None of this can be
demonstrated if no exam session can be created.

Investigation found:

- `services/exam/app/migrations/005_seed_writing_questions.sql` is **0
  bytes** — a seed file that was never filled in.
- No other migration inserts rows into the `questions` table.
- Questions are only ever created through the OCR ingestion pipeline
  (`services/exam/app/ingestion/`), which has no CLI entry point and no HTTP
  route wired to it in normal operation — `QuestionIngestionService` /
  `IngestionService` is only instantiated from `tests/test_ingestion.py`.
- A former 1.6 MB file at the repo root initially looked like plausible OCR
  input, but inspection proved it was a Trello export. It was later removed
  during repository cleanup and was never a valid Exam data dependency.
- Session creation (`get_random_unseen_question` in
  `app/services/session_service.py`) will find nothing and fail outright if
  the `questions` table is empty for `skill_area = 'reading'`.

## Why This Matters

This is the single highest-uncertainty item in the entire demo-readiness
plan and the one with the largest blast radius if it fails: if no Reading
question data exists, `POST /api/exam/sessions` fails, the frontend shows a
raw `alert("Unable to start exam.")`, and the demo loses its best 90
seconds. Because the outcome (does the ingestion pipeline actually work
against real data, or do we need a hand-authored seed) is not knowable in
advance, this must be attempted first, not last — if it fails, the whole
demo script needs to be rewritten, and that needs to happen on day one of
implementation, not the night before the demo.

## Scope

**In scope:**
- Getting one complete, gradable Reading test into the `questions` table.
- Verifying the full Reading exam cycle (create → answer → submit → grade →
  results) works end-to-end against that data, twice, from a cold service
  start.
- A short runbook note capturing which route was used and any operational
  caveats (e.g., seen-question tracking).

**Out of scope:**
- Building a general-purpose ingestion CLI or HTTP route (only attempt this
  if it is fast; otherwise abandon in favor of a hand-authored seed).
- Listening exam data (tracked separately in Phase 3 — Listening exam build
  is out of scope for this demo).
- Fixing or extending the OCR parsers themselves.

## Files Expected to Change

```
services/exam/app/migrations/008_seed_demo_reading_test.sql       (new)
services/exam/scripts/ingest_local.py                             (new, only if Route A succeeds)
docs/dorgham-context/DEMO_RUNBOOK.md                               (new or appended)
```

## Detailed Implementation Plan

Attempt the following two routes **in order** and stop at the first success.
Timebox Route A strictly — do not let pipeline debugging eat the budget for
the more reliable fallback.

### Route A — Run the existing ingestion pipeline (30-minute timebox)

Write a small one-off script that instantiates `QuestionRepository(db.pool)`
and `QuestionIngestionService`, then calls
`ingest(content, skill_area="reading")` against the contents of
the former repo-root export, run inside the `goa-exam-1` container
(so it shares the container's DB connection config).

The existing parsers are already unit-tested and known to produce correct
output against their own fixtures — `ReadingParser` is asserted (in
`tests/test_ingestion.py`) to produce 40 questions across 3 passages with 6
distinct question types correctly classified, given a fixture in the
expected Cambridge OCR text shape.

**If the JSON file's actual shape does not match what `parse_text` expects**
(e.g., it's structured JSON rather than the raw OCR text string the parser
expects, or its section markers differ), **abandon Route A immediately**.
Do not attempt to modify or debug the OCR parser under demo time pressure —
that is real engineering work with its own risk profile and belongs in a
future ticket, not this plan.

### Route B — Hand-authored SQL seed (recommended fallback)

Insert one row directly into `questions` via a new migration file. The
schema (from `001_create_exam_tables.sql`) is:

- `book_ref` (text), `test_number` (int), `exam_type` (`'academic'` or
  `'general'`), `skill_area` (`'reading'`), `passage_text` (text),
  `audio_s3_key` (text, null for reading), `questions` (jsonb, not null),
  `answer_key` (jsonb, not null).
- A unique constraint on `(book_ref, test_number, skill_area)` backs the
  repository's `upsert_question` — the seed migration can use a plain
  `INSERT` since this is a one-time seed, not an upsert path.

Content requirements, driven directly by what the frontend actually renders
and consumes:

- **`passage_text`**: three passages joined by the literal delimiter
  `---` (this matches what `ReadingParser` emits — `\n\n---\n\n` — and what
  `lib/reading-api.ts`'s `splitPassages` function splits on and trims).
  Write each passage to roughly 250–350 words: long enough that the
  independently-scrollable passage panel and the text-highlighting feature
  visibly do something, short enough to author by hand in a reasonable
  amount of time.
- **`questions`**: 12–15 entries, deliberately **not** the full 40 — 40
  questions is not demoable in a 6–8 minute live session, and
  `normalizeReadingQuestions` (in `lib/normalizeReadingQuestions.ts`)
  handles any question count without assumption. **Deliberately span all
  five question-type renderers** (Multiple Choice, Matching,
  True/False/Not Given, Fill-in-the-Blank, Short Answer) — the point of
  showing this feature in the demo is proving every Cambridge question
  type is implemented, and a seed that only exercises one type wastes that.
  Field names (`number`, `question_type`, `section`, etc.) must be derived
  exactly from `app/types/reading.ts` and the normalizer's expectations, not
  guessed — read both files before authoring the JSON.
- **`answer_key`**: must align with what `grade_reading` (the server-side
  grading function referenced from `services/exam/app/api/reading.py`)
  expects, so the per-question green/red breakdown on the results page is
  actually correct rather than uniformly wrong.

**Deliberately engineer an uneven score distribution.** The results view
computes a question-type breakdown that highlights the single weakest
type and links to a "practise this type" action. If the seed answers are
authored (or the demo is played) such that, say, all Multiple Choice
questions are answered correctly but two True/False/Not Given questions are
answered incorrectly, the "62% on TFNG — practise this" panel becomes a
real, earned insight during the demo rather than a flat, uninteresting
100%. This is a content-authoring decision, not a code change, but it should
be made deliberately when writing the answer key and when scripting which
answers the presenter will actually select live.

## Edge Cases

- The `questions` table's original `CHECK` constraint (in
  `001_create_exam_tables.sql`) restricts `skill_area` to
  `('reading', 'listening')` only; a later migration
  (`004_allow_writing_speaking_questions.sql`) widens this. Confirm the
  actual constraint state in the running database before assuming any
  particular skill_area value is insertable — this affects Route A only if
  it also seeds non-reading skills, but verify regardless.
- `get_random_unseen_question` tracks per-user seen questions. With only one
  seeded test, **a second Reading exam attempt by the same user account will
  find nothing** and the second attempt will fail exactly like the
  zero-data case this task is fixing. This must be documented explicitly in
  the runbook: **do not run the Reading demo twice from the same account**
  during rehearsal or on the day — either seed two distinct tests, or always
  use a fresh account per Reading-exam run.
- If Route A partially succeeds (parses but produces malformed
  `questions`/`answer_key` JSON), do not attempt partial fixes — fall
  through cleanly to Route B rather than shipping malformed data.

## Acceptance Criteria

- `POST /api/exam/sessions` with `skill_area: reading` returns a session
  with a populated `first_question_set`.
- The exam shell renders 3 passages, section tabs, and at least 12 questions
  spanning at least 4 distinct question-type renderers.
- Submitting returns `band_score`, `raw_score`, `per_question_result`, and
  `section_breakdown` in the response.
- The results page renders section-breakdown bars, per-question
  correct/incorrect rows, and a question-type breakdown that identifies a
  non-trivial (not 100%, not 0%) weakest type.
- The full create → answer → submit → results cycle succeeds **twice**,
  from two different fresh user accounts, starting from a cold
  `docker compose up`.

## Verification Steps

1. Apply the seed migration (or run the Route A ingestion script) against
   the running Postgres instance.
2. Confirm via `psql`: `SELECT count(*) FROM questions WHERE skill_area = 'reading';`
   returns at least 1.
3. From `/exam` in the frontend, click "Take Exam" on the Reading card.
4. Confirm the passage panel scrolls independently of the question panel;
   select passage text and confirm the highlight applies and persists
   locally.
5. Answer questions of at least four different types; switch to Section 2
   and back to Section 1; confirm all answers survived the switch.
6. Click a question number in the navigation sidebar; confirm it jumps to
   that question and that filled/empty circle states are accurate.
7. Submit; confirm the confirmation modal reports the correct unanswered
   count; confirm the submission; confirm the results page renders fully
   with real (not placeholder) data.
8. Repeat the entire cycle from a second, freshly registered account to
   confirm reproducibility from a cold state.

## Dependencies

None — this is the first task in execution order specifically because
nothing else depends on it, and its outcome (success or failure) may change
priorities for the rest of the plan.

## Estimated Effort

1.5–2 hours (front-loaded: budget the discovery time for Route A, not just
the fallback implementation).

## Risk

**Medium.** Not because the change itself is dangerous (a seed migration is
purely additive), but because the *outcome* is genuinely uncertain until
attempted. Budget for the possibility that Route A fails and Route B is
required.

## Status

Completed. Route A was attempted and abandoned (the former repo-root file was
a Trello board export, not
Cambridge OCR text). Route B implemented:
`services/exam/app/migrations/008_seed_demo_reading_test.sql` seeds one
complete, gradable Reading test (15 questions across all 5 renderer types,
5 per section). Verified live against the running stack: migration applies
cleanly and idempotently, and the full create → answer → submit → grade
cycle succeeded twice from two independent fresh accounts, including a
deliberately uneven score producing a real "weakest question type" result.
Operational notes and known limitations (a pre-existing question bank found
in this environment's Postgres volume, random test selection among all
scorable tests, and a band-score ceiling caused by the seed's reduced
question count) are documented in `docs/dorgham-context/DEMO_RUNBOOK.md`.

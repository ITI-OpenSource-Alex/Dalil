# GOA-058 Implementation Report

**Ticket:** GOA-058 — Writing exam UI — dual task with word counter, timer split, and stimulus
**Service:** Frontend (TypeScript) · **Priority:** P1 · **Story points:** 3
**Branch base:** `dev` @ `31f71ff`
**Status:** ✅ **Complete for the agreed scope** — see [§12](#12-final-status).
**Revision 2** — two follow-up items delivered: (a) Academic Task 1 stimulus **image support postponed by team decision** and removed cleanly, (b) the **HTTP 500 on writing submission fixed at its root cause**. See [§13](#13-revision-2--postponed-images--the-500-fix).

> **Read this if you have never seen GOA before.** This document assumes no prior
> knowledge of the codebase. Every claim about existing behaviour was verified by
> reading or executing the code at the commit above, not from memory or from the
> project's own documentation (which, as [§8.7](#87-should-fix--documentation-drift)
> notes, has drifted).

---

## Table of contents

1. [Ticket summary](#1-ticket-summary)
2. [Architecture overview](#2-architecture-overview)
3. [Every file modified](#3-every-file-modified)
4. [New components](#4-new-components)
5. [API changes](#5-api-changes)
6. [State flow](#6-state-flow)
7. [Acceptance criteria checklist](#7-acceptance-criteria-checklist)
8. [Backend issues discovered](#8-backend-issues-discovered)
9. [Files NOT modified intentionally](#9-files-not-modified-intentionally)
10. [Testing](#10-testing)
11. [Discussion notes](#11-discussion-notes)
12. [Final status](#12-final-status)
13. [Revision 2 — postponed images + the 500 fix](#13-revision-2--postponed-images--the-500-fix)

---

## 1. Ticket summary

### What this ticket does

It builds the user interface for sitting the **IELTS Writing exam**: two tasks
presented as tabs, each with the material to write about, a plain textarea, a live
word counter, a recommended-time indicator, and a per-task submit that produces
immediate colour-coded feedback — followed by a combined results page showing how
the two task bands were weighted into one overall band.

### Why it exists

The backend for this already existed and nothing used it.

A previous ticket (GOA-053) built a complete per-task Writing exam backend: submit
one task, get it graded immediately, keep the session open, submit the second, get a
weighted combined result. The frontend that was supposed to consume it was a
**placeholder** — two textareas side by side in a grid, no word counter, no
stimulus, no per-task submit, and a results page that displayed *hardcoded fake band
scores* (`"Task 1 (Band 7.0)"`) to every candidate regardless of what they wrote.

GOA-058 is the ticket that makes that backend reachable by a human.

### The user problem it solves

IELTS Writing is 60 minutes for two tasks that are marked differently and weighted
differently. A candidate needs four things the placeholder did not provide:

1. **To see what they are writing about.** Academic Task 1 is "describe this chart" —
   without the chart the task is meaningless. General Training Task 1 is a letter
   scenario, which is prose.
2. **To know if they have written enough.** IELTS penalises responses under 150 words
   (Task 1) / 250 words (Task 2) under the Task Achievement criterion. Discovering
   that after submitting is useless.
3. **To manage their own time.** The exam gives one 60-minute clock for both tasks.
   The standard split is 20 minutes on Task 1, 40 on Task 2 — mirroring the 33/67
   mark weighting.
4. **Not to lose exam time waiting for a computer.** Grading one task means four
   parallel LLM calls, which take tens of seconds. If the UI blocked during that, it
   would be stealing time from a timed exam. This is why the AC insists Task 2 stays
   editable and there is **no blocking spinner** — and why the backend was built with
   per-task submit in the first place.

---

## 2. Architecture overview

### 2.1 The services involved

```
                        ┌────────────────────────────────┐
                        │  Browser — Next.js :3000       │
                        │  /exam → /exam/shell → results │
                        └───────────────┬────────────────┘
                                        │ REST, credentials: "include"
                                        │ (auth rides on HttpOnly cookies)
                                        ▼
                    ╔═══════════════════════════════════════╗
                    ║  GATEWAY (Go/Fiber) :8080             ║
                    ║  CORS · JWT · rate limit · holds       ║
                    ║  INTERNAL_API_KEY server-side          ║
                    ╚═══════════════════╤═══════════════════╝
                                        │ + X-Internal-Api-Key
                                        ▼
                    ┌───────────────────────────────────────┐
                    │  EXAM SERVICE (FastAPI)               │
                    │  owns: sessions, the clock, what was  │
                    │  submitted, the 33/67 weighting       │
                    └───────────────────┬───────────────────┘
                                        │ server-to-server ONLY
                                        │ POST /essays/evaluate/exam
                                        ▼
                    ┌───────────────────────────────────────┐
                    │  WRITING SERVICE (FastAPI) :8000      │
                    │  owns: judgement. 4 criterion agents  │
                    │  in parallel → bands + inline issues  │
                    └───────────────────┬───────────────────┘
                                        ▼
                                  Anthropic API
```

**Why the browser never calls the Writing service directly.** Three reasons, all
load-bearing: (a) it would let a client fabricate an evaluation for a session it does
not own; (b) the exam service must *persist the response before grading it*, which is
what makes the exam auditable; (c) the Writing service's exam endpoint is not routed
by the Gateway at all — it is an internal endpoint.

### 2.2 The full flow, from "Take Exam" to results

```
Browser         /exam page      Gateway        Exam svc       Writing svc    Anthropic
  │                 │              │              │                │             │
  │ click Writing   │              │              │                │             │
  ├────────────────▶│              │              │                │             │
  │        POST /api/exam/sessions ├─────────────▶│ pick question  │             │
  │                 │              │              │ INSERT session │             │
  │◀─── {session_id} ──────────────┤              │                │             │
  │  sessionStorage["active_exam_session"] = {...}│                │             │
  │  router.push(/exam/shell?session=…)           │                │             │
  │                 │              │              │                │             │
  │  ═══ EXAM SHELL MOUNTS ═══     │              │                │             │
  │        GET /api/exam/sessions/:id ───────────▶│                │             │
  │◀── {remaining_time_seconds, questions[…]} ────┤                │             │
  │  useExamTimer starts · heartbeat every 60s ──▶│                │             │
  │  <WritingExam> renders: tabs, stimulus, textarea, counter      │             │
  │                 │              │              │                │             │
  │  ─── candidate types Task 1; counter updates live (local state only) ───     │
  │                 │              │              │                │             │
  │  click "Submit Task 1"         │              │                │             │
  │    PUT /api/exam/sessions/:id/submit ────────▶│                │             │
  │    {answers:{}, task_number:1, essay_text}    │ word_count     │             │
  │                 │              │              │ penalty_flag   │             │
  │                 │              │              │ UPSERT response│             │
  │                 │              │              ├───────────────▶│ 4 agents ──▶│
  │                 │              │              │                │◀────────────┤
  │                 │              │              │◀─ evaluations ─┤             │
  │                 │              │              │ UPDATE eval    │             │
  │◀── {status:"task_submitted", overall_band, evaluations[…]} ────┤             │
  │                 │              │              │                │             │
  │  Task 1 tab → collapsed TaskResultCard.                        │             │
  │  Session stays in_progress. Timer keeps running.               │             │
  │  ★ TASK 2 EDITABLE THE ENTIRE TIME. NO OVERLAY. ★              │             │
  │                 │              │              │                │             │
  │  click "Submit Task 2"         │              │                │             │
  │    PUT …/submit {task_number:2} ─────────────▶│  … same again …│             │
  │                 │              │              │ both rows exist│             │
  │                 │              │              │ → submit() + mark_scored()   │
  │◀── {status:"submitted", …} ───────────────────┤                │             │
  │  router.push(/exam/results?session=…&skill=Writing)            │             │
  │                 │              │              │                │             │
  │    GET /api/exam/sessions/:id/result ────────▶│ _get_writing_result()        │
  │                 │              │              │ round((t1+2·t2)/3·2)/2       │
  │◀── {overall_band, tasks:{1:{…},2:{…}}} ───────┤                │             │
  │  <CombinedWritingResults>: big band, formula, two cards        │             │
```

### 2.3 The one architectural idea that explains everything

> **Task 1 is graded while Task 2 is still being written.**

Every structural decision in this ticket descends from that single fact:

| Consequence | Why |
|---|---|
| Both drafts live in `WritingExam`, above the tabs | Tabs show one task at a time; if drafts lived in the panels, switching tabs would destroy a half-written response |
| Both tab panels stay mounted (`hidden`, not unmounted) | Same reason, one level deeper — React unmounts conditionally-rendered children |
| Submit status is **per task** and never leaves `WritingExam` | The shell shows a full-screen overlay when *its* status is `"evaluating"`; Task 1 must never reach that state |
| Writing opts out of the shell's generic "Submit Exam" button | There is no single submit action — the session completes when the second task lands |
| The Task 1 card is fed from the **submit response**, not `GET /result` | `GET /result` returns 404 until both tasks exist, by design |

---

## 3. Every file modified

### 3.1 `services/frontend/lib/writing-exam.ts` — **NEW**

**Why this file exists.** It is the single home for every *rule* in the Writing exam:
how a word is counted, what the targets are, what the warning says, how criteria are
ordered, and how the weighting sentence is phrased. It contains no React and no
`fetch`, so it can be unit-tested under vitest with no DOM and no network.

This follows an existing convention: `lib/reading-grading.ts` and
`lib/reading-results.ts` do exactly the same for the Reading exam, each with a
colocated `.test.ts`. **The ticket's requirement to unit-test the word counter is
itself the argument for this file** — a counter buried in a component needs a
rendered DOM to test.

**Everything it exports:**

| Export | What it is | Why it exists |
|---|---|---|
| `TASK_WORD_TARGETS` | `{1: 150, 2: 250}` | The IELTS minimums |
| `TASK_SUGGESTED_MINUTES` | `{1: 20, 2: 40}` | The standard 20/40 split of the hour |
| `TASK_WEIGHT_PERCENT` | `{1: 33, 2: 67}` | Displayed in the formula and the chips |
| `UNDER_MINIMUM_WARNING` | The exact AC string | Frozen so an incidental edit can't silently reword a user-facing claim about marking |
| `countWords(text)` | `text.trim().split(/\s+/).filter(Boolean).length` | See below |
| `wordCountState(count, task)` | `"below"` \| `"met"` | Drives orange/green |
| `isUnderMinimum(count, task)` | boolean | Drives the warning |
| `elapsedMinutes(limit, left)` | number | Drives the pacing indicator |
| `CRITERION_LABELS` / `CRITERION_ORDER` | display names, canonical order | So criteria always list in the same order regardless of which of the four parallel agents finished first |
| `toEssayIssues(evaluations)` | field-name adapter | See §3.1.2 |
| `topIssuePerCriterion(evaluations)` | one headline finding per criterion | Feeds the collapsed card |
| `formatBand(n)` | `n.toFixed(1)` | IELTS always reports one decimal |
| `formatWeightedFormula(t1, t2, overall)` | the AC's sentence | See §3.1.3 |

#### 3.1.1 `countWords` — why it is deliberately naive

The ticket specifies the algorithm exactly, and it has a surprising property:

```ts
countWords("hello , world")   // → 3, because "," is its own token
```

**That is correct and must not be "fixed".** The exam service decides the
under-length penalty with Python's `len(essay_text.split())`, which splits on the
same arbitrary-whitespace runs and also counts a lone comma. A cleverer client-side
counter would disagree with the server about whether a response was penalised — and a
counter that contradicts the penalty flag is worse than one that counts a comma. The
unit test pins this behaviour explicitly so a future contributor cannot "improve" it
by accident.

#### 3.1.2 `toEssayIssues` — the adapter, and why it is here

The two sides of the app describe the same thing with different names:

```
Writing service emits           EssayHighlighter (GOA-043) consumes
─────────────────────           ────────────────────────────────────
inline_issues: [                issues: [
  { text,                         { text,
    issue_type,        ───────▶     issue,
    suggestion,                     suggestion,
    start_char,                     start,
    end_char }                      end,
]                                   criterion }
                                ]
```

Feeding the raw payload straight into `EssayHighlighter` renders **zero highlights
and throws no error** — the silent-failure case. The translation happens here, at the
boundary, rather than by renaming fields on either side, because `EssayHighlighter`
and `lib/writing-api.ts` are the *chat* writing path's contract and are covered by a
174-line unit test written for GOA-043.

#### 3.1.3 `formatWeightedFormula` — why `overallBand` is a parameter

It takes the overall band as an argument instead of computing it. The exam service
already applies `round((t1 + 2*t2) / 3 * 2) / 2` and **persists that value against
the session**. Recomputing it in the browser would create a second implementation of
a marking rule; the day the two drift, a candidate is shown arithmetic that does not
add up. The formula string exists to *explain* the number, never to produce it.

Verified against the ticket's own worked example:

```
(6.5 + 2 × 7.0) / 3 = 6.8333…  →  ×2 = 13.666…  →  round = 14  →  /2 = 7.0
rendered: "(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0"   ✅ exact match
```

---

### 3.2 `services/frontend/lib/normalizeWritingTasks.ts` — **NEW**

**Why this file exists.** The session payload's `questions` array arrives in **two
genuinely different shapes**, and the old placeholder code assumed one of them
positionally.

```
SHAPE A — every ingested Cambridge book        SHAPE B — the shape submit expects
(writing_parser.py)                            (_resolve_task_context reads ["task1"])
[                                              [{
  { number: 1, prompt, instructions },           task1: { prompt, image_s3_key },
  { number: 2, prompt, instructions }            task2: { prompt }
]                                              }]
```

Shape B arrives wrapped in a single-element array because the exam service's
`_question_list` wraps a bare dict on the way out.

The old code did `session.questions[0].questions[0].prompt` — which silently
mis-renders Shape B (it would stringify the whole wrapper object) and **throws** on
any book that parsed fewer than two tasks.

**Follows an existing convention:** `lib/normalizeReadingQuestions.ts` does the same
job for Reading — one place where messy backend shapes become one clean UI shape.

| Function | Purpose |
|---|---|
| `normalizeWritingTasks(questionSets)` | Detects the shape, returns up to 2 `NormalizedWritingTask` |
| `findWritingTask(tasks, n)` | Looks up one task; `undefined` if the book yielded fewer than two |
| `readStimulusUrl(source)` *(private)* | Accepts `stimulus_image_url` / `stimulusImageUrl` / `image_url` / `imageUrl` |

**Why `readStimulusUrl` accepts four spellings.** No backend response contains this
field *at all* yet (see [§8.1](#81-must-fix--no-stimulus-image-exists-anywhere-in-the-pipeline)),
so there is no established name to match. Accepting the plausible variants means
whichever one the backend ticket eventually ships works with no frontend change, and
no guess can be wrong. `taskNumber` is read from the payload's own `number` field when
present so array order alone cannot swap the two tasks.

---

### 3.3 `services/frontend/lib/exam-api.ts` — **MODIFIED (purely additive)**

**Why this file exists.** The typed client for every exam endpoint. Module-level
`API_BASE` pointing at the Gateway, a shared `headers`, a shared
`fetchOptions = { credentials: "include" }`, and one exported `async function` per
endpoint that throws on `!response.ok`. No React Query, no SWR — this repo has no
data-fetching library and this ticket did not introduce one.

**Why it needed modification.** The existing `submitSession` posts `{ answers }`. The
Writing submit needs `task_number` and `essay_text` **at the top level of the body**
and 400s otherwise.

**What was added — types:**

| Type | Notes |
|---|---|
| `WritingInlineIssue` | `{ text, issue_type, suggestion, start_char, end_char }` — the writing service's real names |
| `WritingCriterionEvaluation` | `{ criterion, band_score, feedback, improvement_tip?, word_count?, inline_issues }` |
| `WritingSubmitResponse` | `{ session_id, task_number, status, overall_band, word_count, penalty_flag, evaluations? }` |
| `WritingTaskResult` | one task's record inside the combined result |
| `WritingResultResponse` | `{ session_id, user_id, skill_area, overall_band, tasks }` |

`evaluations` is optional (`?`) so a frontend deployed against an older exam service
degrades the card to a band score instead of crashing.

**What was added — functions:**

```ts
submitWritingTask(sessionId, taskNumber, essayText) → WritingSubmitResponse
  PUT /api/exam/sessions/:id/submit
  body: { answers: {}, task_number, essay_text }
```

`answers: {}` is not filler — `SubmitAnswersRequest.answers` is a **required** field
on the exam service's Pydantic model with no default, so omitting it is a 422.

```ts
getWritingResult(sessionId) → WritingResultResponse
  GET /api/exam/sessions/:id/result   (cache: "no-store")
```

**Why a new function instead of extending `submitSession`.** `submitSession` is
called by the Reading and Speaking paths. Adding optional `task_number` /
`essay_text` parameters for one caller makes a shared function's contract depend on
who is calling it — the standard way shared modules rot. Nothing existing was
changed, so the blast radius is zero.

---

### 3.4 `services/frontend/app/exam/shell/page.tsx` — **MODIFIED**

**Why this file exists.** The exam-taking chrome shared by **all four skills**:
header, timer, heartbeat, submit modal, and the `switch` that decides which skill's
UI to render. It is the highest-blast-radius file in this ticket.

**Why it needed modification.** It contained the placeholder Writing UI inline.

#### Change 1 — removed `writingInput` state

```diff
- const [writingInput, setWritingInput] = useState({ task1: "", task2: "" });
```
Drafts moved into `WritingExam`, which is the only component that needs them.

#### Change 2 — added `writingForceSubmit`, mirroring Reading's existing mechanism

```ts
const [writingForceSubmit, setWritingForceSubmit] = useState(0);
```

A counter, not a boolean, so each expiry is a distinct value the child can react to.
This is not a new invention — `readingForceSubmit` already worked exactly this way.

#### Change 3 — `executeSubmission` is no longer Writing-shaped

It previously posted `{ task1, task2 }` — a payload the backend rejects. It is now
the generic whole-exam submit for skills with no submit flow of their own, and it
resets `status` to `"in_progress"` on failure (previously it left the user stuck
under a permanent overlay after an error).

#### Change 4 — `handleWritingCompleted`

```ts
const handleWritingCompleted = useCallback(() => {
  router.push(`/exam/results?session=${sessionId}&skill=Writing`);
}, [router, sessionId]);
```

`useCallback` is required, not cosmetic: `WritingExam` calls it from inside a
`useEffect` that lists it as a dependency, so an unstable identity would re-fire the
effect on every render.

#### Change 5 — `handleTimeUp` gains a Writing branch

```ts
if (examConfig.skill === "Writing") { setWritingForceSubmit(n => n + 1); return; }
```

Only `WritingExam` knows which of the two tasks are already evaluated and holds each
one's text. **The pre-existing `if (!examConfig) return;` guard above it was left
untouched** — it prevents a spurious time-up firing on mount while the timer is still
seeded with `0`, a bug whose history is documented in `useExamTimer.ts`.

#### Change 6 — `secondsLeft` is now destructured from `useExamTimer`

The hook already returned it; the shell simply never used it. **No change to the
hook.**

#### Change 7 — Writing opts out of the header's "Submit Exam" button

Reading already opted out. Writing joins it, for a different reason recorded in the
comment: there is no single submit action to offer, and a generic submit could only
post an empty payload over the top of the real per-task flow.

#### Change 8 — the placeholder block (48 lines) replaced with 8

```tsx
{examConfig.skill === "Writing" && (
  <WritingExam
    sessionId={sessionId} session={session} examType={examConfig.type}
    secondsLeft={secondsLeft} forceSubmitSignal={writingForceSubmit}
    onCompleted={handleWritingCompleted}
  />
)}
```

**Deliberately untouched in this file:** the heartbeat effect, the Suspense boundary,
Reading's unpadded container carve-out, the `evaluating` overlay markup, and the
submit-confirmation modal.

---

### 3.5 `services/frontend/app/exam/results/page.tsx` — **MODIFIED**

**Why this file exists.** The post-exam results page for every skill.

**Why it needed modification.** Two independent defects:

1. It rendered **hardcoded fake data** for Writing — `"Task 1 (Band 7.0)"`,
   `"Task 2 (Band 7.5)"` and invented feedback prose, shown to every candidate
   regardless of what they wrote.
2. `getResult` is typed `ExamResultResponse` (`band_score`, `raw_score`), but the
   exam service branches to `_get_writing_result` for Writing and returns
   `{ overall_band, tasks }`. So `result.band_score` was `undefined`, the banner
   rendered empty, and the profile sync posted `bandScore: undefined`.

> **A lesson worth internalising:** TypeScript did not catch this. `response.json()`
> returns `any`; a hand-written API interface is a *claim* about the server, not a
> proof. Always verify the shape against the producer.

**What changed — a third data-loading branch:**

```
skill === "Reading"  → read sessionStorage (no GET endpoint exists)   [unchanged]
skill === "Writing"  → getWritingResult(sessionId)                    [NEW]
otherwise            → getSession + getResult                         [unchanged]
```

The Writing branch mirrors Reading's structure exactly, including the deliberate
fire-and-forget on the profile sync with a comment explaining that a sync failure
must not stop a candidate seeing their result.

**What changed — a third render branch**, returning `<CombinedWritingResults>`
inside the same `Sidebar` + fade-in shell the Reading branch uses. The fake block was
deleted and replaced with a comment recording what used to be there and why it is
gone, so nobody re-adds it.

---

### 3.6 `services/frontend/components/chat/essay-highlighter.tsx` — **MODIFIED (export only)**

**Why this file exists.** GOA-043's inline highlighter: renders essay text with
coloured `<mark>` spans and Radix tooltips, resolving overlapping ranges
first-match-wins.

**Why it needed modification.** Its `CRITERION_COLOURS` map is *already exactly* the
palette GOA-058 requires:

| Criterion | This file's colour | AC requirement |
|---|---|---|
| `grammar` | `rgba(255, 77, 77, …)` red | Grammar → red ✅ |
| `vocabulary` | `rgba(59, 130, 246, …)` blue | Vocabulary → blue ✅ |
| `cohesion` | `rgba(255, 140, 0, …)` orange | Cohesion → orange ✅ |
| `task_response` | `rgba(139, 92, 246, …)` purple | Task Response → purple ✅ |

It was module-private. The alternative to exporting it was defining a second palette
in the Writing components — which would drift, and the entire point of colour coding
is that a student learns one vocabulary that means the same thing everywhere.

**Exactly what changed:** `const CRITERION_COLOURS` → `export const CRITERION_COLOURS`,
and `DEFAULT_COLOUR` → `export const DEFAULT_CRITERION_COLOUR` (renamed on export
because `DEFAULT_COLOUR` is too generic for a public name). One internal reference
updated. **No values, no rendering, and no behaviour changed** — confirmed by the
GOA-043 unit test still passing untouched.

---

### 3.7 `services/exam/app/services/writing_client.py` — **MODIFIED** 🔴 critical fix

**Why this file exists.** The Exam service's HTTP client for calling the Writing
service's `POST /essays/evaluate/exam`.

**Why it needed modification.** **The two services did not agree on the response
shape, and every Writing task submit failed with an unhandled HTTP 500.**

This was not in the ticket, not in the onboarding document, and not caught by any
existing test. It was found by reading both schemas side by side and then proving it:

```
$ python -c "ExamTaskEvaluationResponse.model_validate(<real writing payload>)"
VALIDATION FAILED: ValidationError
1 validation error for ExamTaskEvaluationResponse
evaluations.0.highlighted_issues
  Field required [type=missing, ...]
```

**Root cause.** The client modelled `highlighted_issues: [{issue, start, end}]` — a
shape the Writing service **has never emitted**. It returns
`inline_issues: [{issue_type, start_char, end_char}]`. Because
`highlighted_issues` had no default, validating a genuine response raised
`ValidationError`; because the retry loop only catches `HTTPStatusError`,
`TimeoutException` and `NetworkError`, that escaped uncaught, and `_submit_writing`
only handles `WritingServiceError` — so it surfaced as a 500 blaming the exam service
for the writing service's payload.

**Why the existing tests missed it:** the fixture in `test_e2e_exam.py` used the
*client's* incorrect spelling rather than the producer's real payload. A test that
invents its own shape for both sides of a contract cannot detect a contract mismatch.

**What changed:**

1. `HighlightedIssue` → `InlineIssue`, with the Writing service's field names as
   canonical and `AliasChoices` accepting the legacy spellings so anything still
   sending the old shape keeps validating.
2. `CriterionEvaluation` gained `improvement_tip` and `word_count` (both present on
   the real payload, both previously discarded), and `inline_issues` now defaults to
   an empty list — so a criterion the model found nothing to underline cannot fail
   the entire submit.
3. The validation call is wrapped so a future contract drift raises
   `WritingServiceError` → **502 (an upstream failure)** rather than an unhandled 500.
   It is deliberately not retried: a 2xx body the client cannot read is a contract
   problem, not a transient one.

**Blast radius:** Writing exam only. Confirmed backwards-compatible by a test that
validates the legacy shape.

---

### 3.8 `services/exam/app/services/session_service.py` — **MODIFIED (one additive field)**

**Why this file exists.** All exam business logic — session lifecycle, timers,
grading dispatch, the writing sub-flow, and the weighting.

**Why it needed modification.** The AC *"After Task 1 submit … shows band score and
top issue per criterion"* was **unreachable by any client**. `_submit_writing`
computed the full evaluation, persisted it one line earlier, and then dropped it:

```python
return { "session_id", "task_number", "status", "overall_band",
         "word_count", "penalty_flag" }        # ← no evaluations
```

And `GET /{id}/result` cannot fill the gap — it returns **404 until both task rows
exist**, by design, because a "result" for half a paper is not a result.

**What changed — exactly one key:**

```python
"evaluations": [item.model_dump() for item in evaluation.evaluations],
```

**Alternatives considered and rejected:**

| Option | Why rejected |
|---|---|
| A new `GET /sessions/:id/writing/:task` endpoint | New route + new Gateway route + more public surface, for data already in hand |
| Relax `_get_writing_result` to accept one task | Changes the semantics of "result"; riskier and affects the combined path |
| Drop the AC, show only `overall_band` | Fails the acceptance criterion |

This is a backend change on a frontend ticket. It is one additive field on an
endpoint GOA-053 already built, it breaks no existing caller, and **there is no
frontend-only alternative**. It is called out here rather than buried in the diff.

---

### 3.9 `services/exam/tests/test_e2e_exam.py` — **MODIFIED**

**Why it needed modification.** Its `_writing_eval_response` fixture used
`highlighted_issues`, the spelling that caused §3.7. Fixtures pinned to the *consumer's*
assumption instead of the *producer's* schema are how contract bugs hide.

**Changed:** the fixture now mirrors `services/writing/app/schemas.py` exactly
(`inline_issues`, `issue_type`, `start_char`, `end_char`, plus `improvement_tip` and
`word_count`), and `test_exm09_writing_submit_task1_only` now asserts that the submit
response carries all four criteria and that inline-issue field names survive the
round trip.

---

### 3.10 `services/exam/tests/test_writing_client_contract.py` — **NEW**

Seven tests pinning the Exam↔Writing contract to the **producer's** schema:

| Test | Guards against |
|---|---|
| parses a real writing service response | the §3.7 regression returning |
| carries `improvement_tip` and `word_count` | silently dropping fields again |
| serialises on the producer's field names | the frontend reading these keys directly |
| still accepts the legacy spelling | breaking anything on the old shape |
| a criterion with no issues is valid | one clean criterion failing a whole submit |
| a genuinely malformed payload still fails | the aliases making the model accept anything |
| an unreadable 2xx → `WritingServiceError` | an unhandled 500 wearing a 502's job |

---

### 3.11 `services/frontend/test/e2e/exam-flow.spec.ts` — **MODIFIED (test removed)**

The `"Writing exam: Task 1 submission keeps Task 2 active"` test was deleted, for two
reasons — and the second matters more than the first:

1. It asserted `page.locator("textarea").nth(1)` was enabled. With tabs, only the
   active panel's textarea is present, so the assertion is unexpressible.
2. **It never tested anything.** Nothing stubbed `GET /api/exam/sessions/:id`, so the
   shell's session load failed and redirected to `/exam` — a page with no textarea at
   all. Verified by running the suite on a clean checkout: it fails on `dev` today.

The guarantee it *claimed* to cover is now genuinely covered against a stubbed
Gateway in `writing-exam.spec.ts`. A comment in its place records all of this so the
deletion is not mistaken for a lost test.

---

## 4. New components

All under `services/frontend/components/writing/`.

```
WritingExam                     ← orchestrator: state, tabs, submission
├── (tabs, inline)              ← follows components/reading/SectionTabs.tsx
├── WritingTaskPanel  ×2        ← one task's editor
│   └── StimulusPanel           ← chart+zoom (Academic) | scenario text (GT)
└── TaskResultCard              ← replaces a panel once its task is evaluated
    └── EssayHighlighter        ← REUSED from GOA-043, unchanged

CombinedWritingResults          ← results page
└── TaskResultCard  ×2          ← same component, defaultExpanded
    └── EssayHighlighter        ← REUSED
```

### 4.1 `WritingExam.tsx`

**Purpose.** The Writing exam. Owns all state and all submission.

**Responsibilities.** Normalise the question payload · own both drafts · own tab
selection · own per-task submit status and errors · submit tasks · hold evaluation
outcomes · flush unsubmitted tasks on time-up · tell the shell when the paper is done.

**Props**

| Prop | Type | Purpose |
|---|---|---|
| `sessionId` | `string` | For the submit calls |
| `session` | `ExamSessionResponse` | Source of `questions` and `time_limit_seconds` |
| `examType` | `ExamType` | `"Academic"` \| `"General"` — selects the stimulus variant |
| `secondsLeft` | `number` | From `useExamTimer`; drives the pacing indicator |
| `forceSubmitSignal` | `number` | Incremented by the shell on expiry |
| `onCompleted` | `() => void` | Called when both tasks are in |

**State**

| State | Why it lives here |
|---|---|
| `activeTask: 1 \| 2` | Which tab is shown |
| `drafts: Record<1\|2, string>` | **Above the tabs** so a tab switch cannot destroy a draft |
| `status: Record<1\|2, TaskSubmitStatus>` | **Per task** so Task 1 submitting never disables Task 2 |
| `errors: Record<1\|2, string?>` | A failed task must leave the other usable |
| `outcomes: Partial<Record<1\|2, TaskOutcome>>` | Presence of an outcome = that task is done |

**Lifecycle**

- `useMemo` on `normalizeWritingTasks(session.questions)` — the payload is stable; no
  need to re-parse per render.
- `useEffect` on `bothSubmitted` → `onCompleted()`. Derived from state rather than
  fired inside the submit handler, so it cannot double-fire.
- `useEffect` on `forceSubmitSignal` → flush unsubmitted tasks **sequentially**.
  Sequential because each submit triggers four upstream LLM calls; firing both at
  once doubles peak load for no benefit when the candidate is leaving anyway. Guarded
  with `if (forceSubmitSignal === 0) return;` so it never fires on mount. Keyed only
  on the signal (with an explicit `eslint-disable` and a comment) so it fires once per
  expiry, not on every draft keystroke.

**Communication.** Down: props to `WritingTaskPanel` / `TaskResultCard`. Up:
`onCompleted` to the shell. Sideways: `submitWritingTask` from `lib/exam-api.ts`.

**The `hidden` decision.** Both tab panels are always rendered; the inactive one gets
`hidden` plus a `hidden` class. Conditional rendering would unmount the inactive
textarea and destroy its draft, scroll position and selection on every tab glance.
This is the mechanism that makes *"Task 2 remains fully editable"* true rather than
merely intended.

### 4.2 `WritingTaskPanel.tsx`

**Purpose.** One task's editor.

**Responsibilities.** Render the stimulus, a plain textarea, the live word counter,
the under-minimum warning, the recommended-time indicator, and the submit button.

**Props:** `taskNumber`, `task`, `examType`, `value`, `onChange`, `onSubmit`,
`status`, `errorMessage`, `elapsedMinutes`.

**State: none.** Fully controlled. Drafts belong to `WritingExam`; a local
`useState` mirror here would be the classic controlled/uncontrolled desync bug.

Notable details:
- Word counter carries `data-state="below" | "met"` alongside the orange/green class,
  so the E2E can assert the semantic *and* the rendered colour.
- The pacing chip turns amber past the task's budget (Task 1: 0–20 min, Task 2:
  20–60 min).
- Submit is disabled at zero words — submitting an empty task is never intentional.
- If the paper yielded no prompt for this task, it renders an explanatory placeholder
  instead of throwing (the old code threw).

### 4.3 `StimulusPanel.tsx`

**Purpose.** The material a task is written about.

| Variant | Renders |
|---|---|
| Academic + image URL | prompt + `next/image` + Zoom button + modal |
| Academic, no image URL | prompt only (**today's live case** — see §8.1) |
| General Training | prompt as the letter scenario, no image |

**Props:** `task: NormalizedWritingTask`, `examType: ExamType`.
**State:** `zoomed: boolean`.
**Lifecycle:** a `useEffect` binds Escape-to-close only while zoomed, and cleans up.

**Why `unoptimized` on `<Image>`.** The `src` is a pre-signed S3 URL: it expires and
carries per-request credentials in its query string. Routing it through Next's image
optimizer would cache a URL that stops working and key that cache on a signature that
changes every request. This is the *correct* choice, not a shortcut — and it also
avoids needing `images.remotePatterns` for a hostname nobody has provisioned yet.

**Test IDs are task-scoped** (`stimulus-image-1`) because both tab panels stay
mounted, so an unscoped ID matches twice. This was caught by a failing E2E run, not
guessed.

### 4.4 `TaskResultCard.tsx`

**Purpose.** A submitted task, as a compact feedback card. Used in **two places** —
during the exam (collapsed) and on the results page (expanded).

**Props:** `taskNumber`, `overallBand`, `wordCount`, `penaltyFlag`, `evaluations`,
`essayText`, `defaultExpanded = false`.
**State:** `expanded: boolean`, seeded from `defaultExpanded`.

**Why collapsed by default during the exam.** Not a space saving — an exam-design
choice. Once Task 1 is in, the candidate's remaining time belongs to Task 2; pulling
them into a detailed post-mortem is actively harmful. Band + one issue per criterion
is enough to course-correct; the full mark-up is one click away.

**Why `essayText` is a required prop.** Inline highlight offsets are computed
server-side by exact substring search against the submitted text. Rendering
highlights over any other string puts every mark in the wrong place.

**Why `penaltyFlag` comes from the server.** The card reports what was actually
recorded against the submission, so it can never contradict the backend.

### 4.5 `CombinedWritingResults.tsx`

**Purpose.** The finished paper.

**Props:** `result: WritingResultResponse`. **State:** none — pure presentation.

Renders the large overall band (the **server's** `overall_band`), the explicit
weighting formula, 33%/67% chips, and both tasks side by side (`lg:grid-cols-2`,
stacked below `lg`) as expanded `TaskResultCard`s. A missing task renders a
placeholder rather than throwing.

---

## 5. API changes

**No new endpoints. No Gateway changes.** Everything uses routes GOA-053 and GOA-054
already built and the Gateway already proxies (`server.go:113-117`).

### 5.1 `POST /api/exam/sessions` — create session *(unchanged, existing)*

```jsonc
// Request
{ "user_id": "<uuid>", "exam_type": "academic", "skill_area": "writing" }
// Response
{ "session_id": "<uuid>", "first_question_set": { … } }
```
Called by `app/exam/page.tsx` via `createSession()`. Untouched by this ticket.

### 5.2 `GET /api/exam/sessions/:id` — load session *(unchanged, consumed differently)*

```jsonc
{
  "id": "<uuid>", "exam_type": "academic", "skill_area": "writing",
  "status": "in_progress", "time_limit_seconds": 3600,
  "remaining_time_seconds": 3540,
  "questions": [ { "id": "…", "questions": [ /* task prompts */ ] } ]
}
```

**How the frontend uses it:** the shell seeds `useExamTimer` from
`remaining_time_seconds`; `WritingExam` passes `questions` through
`normalizeWritingTasks`. **Why:** the server's `started_at` is the authority on time —
the client countdown is a display convenience, so a reload gets the true remaining
time rather than a restarted clock.

⚠️ This response is where a `stimulus_image_url` *would* live. It does not exist yet
(§8.1). The frontend reads it optionally and degrades.

### 5.3 `PUT /api/exam/sessions/:id/submit` — submit ONE task ⭐

```jsonc
// Request — task_number and essay_text are TOP LEVEL, not inside answers
{ "answers": {}, "task_number": 1, "essay_text": "The chart shows…" }
```

```jsonc
// Response
{
  "session_id": "<uuid>",
  "task_number": 1,
  "status": "task_submitted",        // "submitted" once BOTH tasks are in
  "overall_band": 6.5,
  "word_count": 162,
  "penalty_flag": false,
  "evaluations": [                   // ← ADDED BY THIS TICKET (§3.8)
    { "criterion": "grammar", "band_score": 6.5, "feedback": "…",
      "improvement_tip": "…", "word_count": 162,
      "inline_issues": [ { "text": "have went", "issue_type": "…",
                           "suggestion": "have gone",
                           "start_char": 10, "end_char": 19 } ] }
  ]
}
```

**How the frontend uses it:** `overall_band`, `word_count` and `penalty_flag` become
the card's headline; `evaluations` feeds `topIssuePerCriterion` (collapsed view) and
`toEssayIssues` → `EssayHighlighter` (expanded view); `status === "submitted"`
triggers navigation to results.

**Why `answers: {}`:** required field on the Pydantic model with no default.
**Why one call per task:** the entire point — Task 1 is graded while Task 2 is written.
**Idempotent:** the row is UPSERTed on `(session_id, task_number)`, so a retry is safe.

### 5.4 `GET /api/exam/sessions/:id/result` — combined weighted result

```jsonc
{
  "session_id": "<uuid>", "user_id": "<uuid>", "skill_area": "writing",
  "overall_band": 7.0,
  "tasks": {
    "1": { "response_text": "…", "word_count": 162, "penalty_flag": false,
           "evaluation": { "evaluations": [ … ], "overall_band": 6.5 } },
    "2": { "response_text": "…", "word_count": 271, "penalty_flag": false,
           "evaluation": { "evaluations": [ … ], "overall_band": 7.0 } }
  }
}
```

**404s until both tasks exist** — which is exactly why the Task 1 card is fed from
the submit response instead. **How the frontend uses it:** `CombinedWritingResults`
displays `overall_band` verbatim and renders the formula from the two task bands.

### 5.5 `PATCH /api/exam/sessions/:id/heartbeat` *(unchanged)*

Fired by the shell every 60s. The backend sweeps silent sessions and marks them
`abandoned`, after which submit 403s and the attempt is lost. Deliberately never
throws. Untouched.

---

## 6. State flow

### 6.1 Typing — every keystroke, no network

```
candidate types in the Task 1 textarea
        ↓  onChange
WritingTaskPanel.onChange(value)                       (no local state — controlled)
        ↓
WritingExam: setDrafts(d => ({ ...d, 1: value }))      ← the single source of truth
        ↓  re-render
WritingTaskPanel receives value
        ↓
countWords(value)                                      lib/writing-exam.ts
        ↓
wordCountState(count, 1) → "below" | "met"
        ↓
counter text + orange/green + data-state
isUnderMinimum(count, 1) → show/hide the exact warning string
```

**No network. No debounce. No server round trip.** Local React state re-rendering a
pure function — the cheapest possible path for something that runs on every keystroke.

### 6.2 Switching tabs — why the draft survives

```
click "Task 2" → setActiveTask(2)
        ↓
BOTH panels re-render. Task 1's panel gets hidden + `hidden` class.
        ↓
Task 1's <textarea> IS STILL MOUNTED.  value={drafts[1]} unchanged.
        ↓
switch back → draft, scroll position and selection all intact
```

Had the panels been conditionally rendered, Task 1's textarea would unmount here and
its draft would be gone.

### 6.3 Submitting Task 1 — the critical path

```
click "Submit Task 1"
        ↓
handleSubmitTask(1) → submitTask(1)
        ↓
guard: empty draft → "empty", no call.  already submitted → "submitted", no call.
        ↓
setStatus({ 1: "submitting" })        ← ONLY task 1. Task 2 untouched.
        ↓
submitWritingTask(sessionId, 1, essayText)     lib/exam-api.ts
        ↓
PUT /api/exam/sessions/:id/submit   →  Gateway  →  Exam service
        ↓                                             ↓ word_count, penalty_flag
        ↓                                             ↓ UPSERT exam_writing_responses
        ↓                                             ↓ → Writing service → 4 agents
        ↓                                             ↓ UPDATE evaluation_result
        ↓                                             ↓ 1 of 2 tasks → stay in_progress
{ status:"task_submitted", overall_band, word_count, penalty_flag, evaluations }
        ↓
setOutcomes({ 1: { …, essayText } })   ← essayText kept VERBATIM (offsets depend on it)
setStatus({ 1: "idle" })
        ↓
renderTask(1) now sees an outcome → <TaskResultCard> instead of <WritingTaskPanel>
        ↓
setActiveTask(2)                       ← move the candidate to the work that remains
```

**What deliberately does NOT happen:** the shell's `status` never becomes
`"evaluating"`, so the full-screen `"Analyzing performance..."` overlay never renders.
Task 2's textarea is never disabled — its status is a separate key in a separate
object. This is asserted directly in the E2E.

**On failure:** `status[1] = "error"`, message captured, **draft preserved**, submit
re-enabled, Task 2 entirely unaffected. Also covered by an E2E test.

### 6.4 Submitting Task 2 → results

```
submit task 2 → outcomes now has BOTH keys
        ↓
bothSubmitted === true
        ↓
useEffect → onCompleted()
        ↓
router.push(/exam/results?session=…&skill=Writing)
        ↓
results page: skill === "Writing" branch → getWritingResult(sessionId)
        ↓
GET /api/exam/sessions/:id/result → exam service _get_writing_result()
        ↓          overall_band = round((t1 + 2·t2) / 3 · 2) / 2
        ↓
setWritingResult(...)  ·  sessionStorage.removeItem("active_exam_session")
        ↓                 fire-and-forget profile sync (§8.6)
<CombinedWritingResults>
        ↓
large band  ← result.overall_band          (SERVER's value, never recomputed)
formula     ← formatWeightedFormula(t1, t2, result.overall_band)
two cards   ← <TaskResultCard defaultExpanded>
```

### 6.5 Timer expiry

```
useExamTimer counts to 0 → onTimeUp()
        ↓
shell handleTimeUp():  !examConfig → return       (pre-existing mount guard)
                       Reading     → readingForceSubmit++
                       Writing     → writingForceSubmit++       ← NEW
        ↓
WritingExam useEffect([forceSubmitSignal]):  0 → return (mount)
        ↓
for task of [1, 2] sequentially:  if no outcome → await submitTask(task)
        ↓
onCompleted() → results page
```

---

## 7. Acceptance criteria checklist

| # | Acceptance criterion | Status |
|---|---|---|
| 1 | Two-panel layout: Task 1 and Task 2 as tabs | ✅ Implemented |
| 2 | Academic Task 1: stimulus image above textarea with zoom button | ⚠️ **Frontend complete, blocked on backend data** |
| 3 | General Training Task 1: letter scenario text above textarea | ✅ Implemented |
| 4 | Word counter — live count | ✅ Implemented |
| 5 | Word counter — orange below target (140/240) | ✅ Implemented |
| 6 | Word counter — green at target (150/250) | ✅ Implemented |
| 7 | Recommended time indicator: "Suggested: 20 min for Task 1" | ✅ Implemented |
| 8 | Plain textarea, no rich text formatting | ✅ Implemented |
| 9 | Results: Task 1 and Task 2 side by side | ✅ Implemented |
| 10 | Results: explicit 33/67 weighting | ✅ Implemented |
| 11 | Inline colour-coded feedback (grammar red, vocabulary blue, cohesion orange, task response purple) | ✅ Implemented |
| 12 | After Task 1 submit → compact results card | ✅ Implemented |
| 13 | Card shows band score | ✅ Implemented |
| 14 | Card shows top issue per criterion | ✅ Implemented *(required a backend field — §3.8)* |
| 15 | Card is expandable | ✅ Implemented |
| 16 | Card is collapsed by default | ✅ Implemented |
| 17 | Task 2 remains fully editable while Task 1 evaluation runs | ✅ Implemented |
| 18 | No blocking spinner for Task 1 evaluation | ✅ Implemented |
| 19 | Combined results: large overall band | ✅ Implemented |
| 20 | Combined results: explicit formula `(6.5 × 33%) + (7.0 × 67%) = 6.8 → Band 7.0` | ✅ Implemented |
| 21 | Under-minimum warning, per task, exact wording | ✅ Implemented |
| 22 | Unit tests: multiple spaces / newlines / punctuation | ✅ Implemented |
| 23 | E2E: Academic image displayed, zoom works | ✅ Implemented *(mocked — see AC #2)* |
| 24 | E2E: 148 words → orange, 150 words → green | ✅ Implemented |
| 25 | E2E: both tasks evaluated, weighted band displayed | ✅ Implemented |

**24 of 25 fully delivered. One partially blocked.**

### AC #2 — the blocked criterion, in detail

**What is done (frontend, 100%):** `StimulusPanel` renders the image, the zoom button,
the modal, Escape-to-close and backdrop-close. `normalizeWritingTasks` extracts the URL
under four accepted spellings. `next/image` is configured correctly for pre-signed
URLs. An E2E test proves the image renders and the zoom button works, driven by a
mocked session payload.

**What blocks it (backend / data / infrastructure):**

| Layer | Gap | Verified how |
|---|---|---|
| **Database / data** | No ingested Cambridge writing question carries any image key. The chart survives only as OCR noise inside the prompt text (`"Sodium Saturated fat\nB\nB0\nPRORXRRI"`). `005_seed_writing_questions.sql` is a **zero-byte file**. | Read `data/parsed/IELTS14/writing/test1.json` and the migration |
| **Backend (API)** | `_public_question` returns `passage_text`, `audio_s3_key`, `questions` — no image field, and `QuestionResponse` would strip a top-level addition. | Read `session_service.py:476-490` |
| **Backend (S3)** | Pre-signing exists only for *listening audio* (`S3AudioDeliveryService`). Nothing pre-signs images. | Grepped for `generate_presigned_url` |
| **Infrastructure** | No stimulus images have been uploaded to S3/LocalStack at all. | No upload script exists (only `upload_listening_audio.py`) |

**Why it was not fixed here:** ingesting stimulus images, adding a pre-sign service,
exposing the URL, and re-seeding questions is a multi-point **backend** ticket. This
ticket is `Service: Frontend`. See §8.1 for the recommended fix.

**Current behaviour with real data:** Academic Task 1 renders prompt-only. Nothing
crashes. When the backend field appears, the image and zoom activate with **no
frontend change**.

---

## 8. Backend issues discovered

Every item below was **re-verified against current code during this work**, not
copied from the onboarding document. Two of them are new discoveries.

### 8.1 MUST FIX — No stimulus image exists anywhere in the pipeline

| | |
|---|---|
| **Location** | `services/exam/app/services/session_service.py:476-490`; `services/exam/app/migrations/005_seed_writing_questions.sql` (empty); `services/exam/data/parsed/*/writing/*.json` |
| **Cause** | The stimulus was never ingested, never uploaded to S3, never pre-signed, and never exposed on the session API. |
| **Impact** | Academic Task 1 cannot show a chart. Compounded by §8.2, the Academic Writing exam **cannot complete at all**. |
| **Fix** | (1) Extract/attach stimulus images during ingestion; (2) upload to S3 like `upload_listening_audio.py` does for audio; (3) add a pre-sign step and expose `stimulus_image_url` on the writing task in `_public_question` + `QuestionResponse`; (4) seed the questions. The frontend already reads the field — no frontend change needed. |
| **Priority** | 🔴 **MUST FIX before production** |

### 8.2 MUST FIX — `_resolve_task_context` crashes on real ingested data

| | |
|---|---|
| **Location** | `services/exam/app/services/session_service.py:631-645` |
| **Cause** | `(questions_data or {}).get("task1", {})` assumes `questions` is a **dict**. Every ingested Cambridge book produces a **list**. A non-empty list is truthy, so it stays a list and `.get` raises. |
| **Verified** | Executed against real data: `CONFIRMED AttributeError -> 'list' object has no attribute 'get'` |
| **Impact** | `AttributeError` → **unhandled HTTP 500 on every writing task submit** against real seeded questions. Only the dict-shaped unit-test fixture works. |
| **Fix** | Reuse the existing `self._question_list(...)` normaliser, then select by `number`, falling back to the `task1`/`task2` dict keys. `lib/normalizeWritingTasks.ts` implements exactly this logic on the frontend and can be ported directly. |
| **Priority** | 🔴 **MUST FIX before production** |

### 8.3 MUST FIX — Academic Task 1 hard-fails without a stimulus key

| | |
|---|---|
| **Location** | `services/writing/app/evaluation.py:172-174` |
| **Cause** | `if is_academic_task1 and not stimulus_s3_key: raise EvaluationFailed("Academic Task 1 requires a stimulus image.")` |
| **Impact** | Even after §8.2 is fixed, Academic Task 1 returns **502** until §8.1 lands, because no question has a stimulus key. General Training is unaffected. |
| **Fix** | Land §8.1. Alternatively, downgrade to a warning and evaluate without chart context — but that means marking a "describe this chart" answer without the chart, which is arguably worse than failing loudly. **Recommend fixing §8.1 rather than relaxing this guard.** |
| **Priority** | 🔴 **MUST FIX before production** (resolved by §8.1) |

### 8.4 FIXED IN THIS TICKET — Exam↔Writing response contract mismatch

| | |
|---|---|
| **Location** | `services/exam/app/services/writing_client.py:27-44` (before the fix) |
| **Cause** | The client modelled `highlighted_issues: [{issue, start, end}]`; the Writing service emits `inline_issues: [{issue_type, start_char, end_char}]`. The field was required with no default. |
| **Verified** | Executed `model_validate` against a real payload: `ValidationError … highlighted_issues Field required`. |
| **Impact** | `ValidationError` escaped the retry loop (which catches only HTTP/timeout/network errors) and `_submit_writing` (which catches only `WritingServiceError`) → **unhandled 500 on every writing submit**. Also, `inline_issues` was discarded entirely, so inline colour-coded feedback had **no data**. |
| **Fix applied** | Aliased the model to the producer's real field names, defaulted `inline_issues` to `[]`, carried `improvement_tip`/`word_count` through, and wrapped validation so a future drift is a clean 502. Legacy spelling still accepted. Seven regression tests added. |
| **Priority** | ✅ **Fixed** — was blocking everything |

### 8.5 SHOULD FIX — Gateway timeout is shorter than the work it proxies

| | |
|---|---|
| **Location** | `services/gateway/server.go:46,48` |
| **Cause** | Exam routes use `httpClient` with a **10-second** timeout. A writing submit triggers four parallel LLM calls; the exam→writing client itself allows **30s with 1 retry (up to 60s)**. Streaming routes already get a separate 5-minute client. |
| **Impact** | A realistic Task 1 evaluation (typically 10–30s) exceeds the Gateway's window, returning **502 while both services are still working successfully** — "a gateway timeout wearing an upstream failure's costume", as an earlier commit message put it about the same class of bug. |
| **Fix** | Give the exam handler the existing `streamClient` (or a dedicated ~90s client) at minimum for `PUT /exam/sessions/:id/submit`. One line. |
| **Priority** | 🟠 **SHOULD FIX** — will cause intermittent, confusing failures in any real end-to-end run |

### 8.6 SHOULD FIX — `/api/profile/update-scores` does not exist

| | |
|---|---|
| **Location** | `services/frontend/app/api/` contains only `chat/` routes |
| **Cause** | The route was never built. |
| **Impact** | Every results page (Reading and now Writing) posts to a **404**. Band scores never sync to the profile, so the skill cards on `/exam` show stale numbers. |
| **Fix** | Build the BFF route, or point it at the user service through the Gateway. |
| **Priority** | 🟠 **SHOULD FIX** — pre-existing; the Writing branch deliberately matches Reading's existing fire-and-forget handling rather than inventing new behaviour |

### 8.7 SHOULD FIX — Documentation drift

| | |
|---|---|
| **Location** | `docs/architecture.md` |
| **Cause** | Claims the Exam service is "TypeScript / NestJS" and the Writing service uses "SQLAlchemy" under a NestJS exam service. The Exam service is **Python / FastAPI + asyncpg**. |
| **Impact** | Actively misleads new joiners about which language and framework to expect. |
| **Fix** | Correct the service table. |
| **Priority** | 🟠 **SHOULD FIX** |

### 8.8 NICE TO HAVE — `userId` is hardcoded in the exam entry point

`app/exam/page.tsx:52` uses `"00000000-0000-0000-0000-000000000001"` with a `TODO`.
Every session belongs to the same fictional user. Pre-existing, affects all four
skills, out of scope here. 🟡

### 8.9 NICE TO HAVE — Two parallel criterion naming schemes

The codebase carries both `task_achievement/coherence/lexical/grammar` and
`task_response/cohesion/vocabulary/grammar`, bridged by a `CRITERION_ALIASES` map in
`writing-evaluation-panel.tsx`. GOA-058 uses the second consistently (it is what the
exam endpoint returns). Worth converging eventually. 🟡

### 8.10 NICE TO HAVE — Unmocked E2E tests in `exam-flow.spec.ts`

Two remaining tests ("Reading exam resumes…", "Speaking exam shows evaluating
spinner…") stub nothing, so the session load fails and the shell redirects to `/exam`.
**They fail on a clean `dev` checkout** — verified by stashing all changes and running
the suite. They should be rewritten against mocks like `reading-exam.spec.ts` and
`writing-exam.spec.ts`, or deleted. Out of scope here. 🟡

### 8.11 NICE TO HAVE — Missing test dependencies in the writing service

`services/writing/tests/unit/test_cv_processor.py` and `test_vision.py` fail to import
(`ModuleNotFoundError: No module named 'docx'`, and others). Pre-existing environment
gaps, unrelated to this ticket (no writing-service source was modified). 🟡

---

## 9. Files NOT modified intentionally

| File / area | Why it was left alone |
|---|---|
| `app/hooks/useExamTimer.ts` | Already returns `secondsLeft`; elapsed time is derived from it. Shared by all four skills, and its comments document a real, subtle bug (spurious `onTimeUp` from a stale `secondsLeft`) that a well-meaning refactor could resurrect. |
| `components/chat/essay-highlighter.tsx` — logic | **Reused as-is.** Only two `export` keywords added. Its overlap resolution and rendering are covered by a 174-line GOA-043 unit test that still passes untouched. |
| `components/chat/writing-evaluation-panel.tsx` | Chat-shaped (`Record<string, {band, feedback}>`, paid-tier "improved essay", print CSS). Its *ideas* were reused; the component was not, because bending it to serve both would have made it worse at both. |
| `lib/writing-api.ts`, `lib/writing-stream.ts` | The **chat** writing path (SSE). The exam path goes through the exam service. Changing their types to match the exam contract would break GOA-043. |
| `services/writing/**` (all source) | "Reuse the existing Writing evaluation infrastructure" means exactly this. The 4-agent swarm, prompts, caching and `/essays/evaluate/exam` are untouched. |
| `services/gateway/**` | No new routes needed — `server.go:113-117` already proxies everything. §8.5 is a real issue but is a separate concern with its own blast radius. |
| `components/reading/**`, `lib/reading-*.ts` | Reading's implementation. Its `SectionTabs` **pattern** was followed and its E2E CORS helpers were copied, but no Reading file was edited. |
| `app/exam/page.tsx` | Exam entry point, shared by all skills. Nothing about the landing page changes. |
| `_resolve_task_context` (§8.2) | A real backend bug, but backend-owned and out of this ticket's service boundary. Filed rather than fixed; the frontend equivalent in `normalizeWritingTasks.ts` can be ported straight across. |
| `app/api/**` | Only chat BFF routes exist. Building `/api/profile/update-scores` (§8.6) is out of scope. |
| `next.config.ts` | Not needed — `unoptimized` on the one `<Image>` is the correct handling for pre-signed URLs, so no `images.remotePatterns` entry (and no guessed S3 hostname) is required. |

---

## 10. Testing

### 10.1 Commands executed and results

| # | Command | Result |
|---|---|---|
| 1 | `npx vitest run test/unit/writing-exam.test.ts` | ✅ **27 passed** (new tests, first run) |
| 2 | `npx vitest run` (all frontend unit tests) | ✅ **44 passed**, 4 files |
| 3 | `npx tsc --noEmit` | ✅ **clean** (2 errors found and fixed during development) |
| 4 | `npx next build` | ✅ **Compiled successfully**, TypeScript clean, 16 routes generated |
| 5 | `npx playwright test test/e2e/writing-exam.spec.ts` | ✅ **9 passed** (3 failed on first run; all 3 fixed — see §10.3) |
| 6 | `npx playwright test writing-exam + reading-exam + exam-flow` | ✅ **15 passed, 2 failed** — both failures pre-existing (§10.4) |
| 7 | `npx playwright test test/e2e/reading-exam.spec.ts --repeat-each=2` | ✅ **10 passed** (regression check on the shared shell) |
| 8 | `python -m pytest tests/test_writing_client_contract.py tests/test_e2e_exam.py` (exam) | ✅ **19 passed** |
| 9 | `python -m pytest -q` (entire exam service) | ✅ **233 passed, 3 skipped** |
| 10 | `python -m pytest tests/unit -q` (writing service) | ⚠️ 29 passed, 1 failed, 4 errors — **all pre-existing** `ModuleNotFoundError` (§8.11); no writing-service source was modified |
| 11 | Direct probe: `ExamTaskEvaluationResponse.model_validate(<real payload>)` | ✅ Failed before the fix, passes after — this is how §8.4 was found and proven |
| 12 | Direct probe: `.get("task1")` on real parsed JSON | ✅ `AttributeError` reproduced — proves §8.2 |

**Lint:** this repository has **no ESLint configuration** (`npx eslint` reports
"couldn't find an eslint.config.js") and no `lint` script in `package.json`. Static
checking is `tsc` and the TypeScript pass inside `next build`, both of which are clean.

### 10.2 New tests added

**Unit — `test/unit/writing-exam.test.ts` (27 tests):**

- `countWords`: empty/whitespace-only · multiple spaces · newlines and tabs ·
  **punctuation-only tokens** (pinned to match the server) · punctuation attached to words
- `wordCountState`: 148/149 → below, 150 → met (Task 1); 240/249 → below, 250 → met
  (Task 2); empty → below
- `UNDER_MINIMUM_WARNING`: verbatim string assertion
- `elapsedMinutes`: zero, mid-exam, exhausted, partial-minute flooring, never negative
- `toEssayIssues`: field-name mapping · criterion propagation · empty and missing arrays
- `topIssuePerCriterion`: canonical ordering · prefers inline issue over feedback ·
  falls back to feedback so a criterion never disappears
- `formatWeightedFormula`: **the ticket's exact worked example** · one-decimal
  formatting · server band differing from the raw mean
- `normalizeWritingTasks`: list shape · dict shape · stimulus only on Task 1 · missing
  data · one-task papers · unusable prompts

**E2E — `test/e2e/writing-exam.spec.ts` (9 tests):**

Academic stimulus + zoom + Escape-close · GT scenario text with no image ·
**148 orange / 150 green** (asserting the rendered colour, not just the class) ·
under-minimum warning appears and clears · recommended time per task ·
**drafts survive tab switches** · **Task 1 collapsed card + expandable + Task 2 stays
editable + no overlay** · **both tasks → weighted band + exact formula** ·
failed submit leaves the exam usable.

**Backend — `tests/test_writing_client_contract.py` (7 tests):** see §3.10.

### 10.3 Failures encountered during development, and their real causes

Honest record — three E2E tests failed on first run and each revealed a genuine issue:

1. **Duplicate test IDs.** `getByTestId("stimulus-scenario-text")` matched twice
   because both tab panels stay mounted. → Task-scoped every stimulus test ID. *This
   was a real consequence of the `hidden`-not-unmounted design, found by the test.*
2. **Colour assertion wrong.** I guessed the oklch values. → Probed the running app for
   the actual computed values (Chromium reports Tailwind's oklch as `lab(…)`) and
   asserted those, with a comment recording where they came from.
3. **No highlight rendered.** My fixture gave two issues the same `start_char: 0`;
   `EssayHighlighter` resolves overlaps first-match-wins and drops the loser. → Gave
   the fixture non-overlapping offsets, matching how real offsets are produced
   (substring search, which cannot collide this way).

### 10.4 Pre-existing failures (not caused by this work)

Verified by stashing every change and running the suite on a clean `dev` checkout:

| Test | Clean `dev` | With this work |
|---|---|---|
| `exam-flow.spec.ts` "Reading exam resumes…" | ❌ fails | ❌ fails (unchanged) |
| `exam-flow.spec.ts` "Speaking exam shows evaluating spinner…" | ❌ fails | ❌ fails (unchanged) |
| `exam-flow.spec.ts` "Writing exam: Task 1…" | ❌ fails | *removed — see §3.11* |
| `reading-exam.spec.ts` "passage highlighting is local…" | ✅ passes | ✅ passes (one flaky run; 10/10 on repeat) |

All three `exam-flow` failures share one cause: they stub no network, so the session
load fails and the shell redirects away from the exam (§8.10).

> **Process note, recorded for transparency:** while establishing that baseline I used
> `git stash`, and a partial `stash pop` followed by `stash drop` temporarily lost the
> tracked-file edits. They were recovered in full from the dropped stash commit
> (`3865aef4`) via `git checkout <sha> -- <paths>`, and every suite was re-run
> afterwards to confirm the restored state is correct (rows 2, 3, 4, 6, 9 above were
> all re-executed post-recovery). No work was lost, but the baseline check would have
> been safer as a `git worktree`.

---

## 11. Discussion notes

Talking points for defending this implementation in review.

### 11.1 Why a `lib/writing-exam.ts` instead of logic inside components?

**Why:** the DoD requires unit tests for the word counter, and a pure function tests in
milliseconds with no DOM. It also guarantees the counter, the warning threshold and the
formula have exactly one definition.
**Alternatives rejected:** a `useWordCount` hook (needs a React test renderer for no
benefit); logic inline in each panel (two definitions, guaranteed drift).
**Reused/followed:** the `lib/reading-grading.ts` + colocated `.test.ts` convention.
**Rule followed:** `lib/` = pure logic and API clients; `components/` = rendering.

### 11.2 Why a new `submitWritingTask` instead of extending `submitSession`?

**Why:** `submitSession` is called by the Reading and Speaking paths. Adding optional
`task_number`/`essay_text` for one caller makes a shared contract depend on the caller.
**Alternative rejected:** overloading it — smaller diff, larger blast radius.
**Rule followed:** additive changes to shared modules; blast radius over line count.

### 11.3 Why tabs with both panels mounted, rather than conditional rendering?

**Why:** the AC demands tabs *and* that Task 2 stays fully editable. Conditional
rendering unmounts the inactive textarea and destroys its draft, scroll position and
selection on every tab switch.
**Alternative rejected:** conditional rendering plus draft-restoration effects —
strictly more code to reproduce what the browser does for free.
**Discussion point:** the AC says "two-panel layout … as tabs", which is mildly
self-contradictory. "Tabs" was taken as authoritative (it matches real IELTS), and
"Task 2 remains fully editable" was read as *not disabled, not blocked* rather than
*simultaneously visible*.

### 11.4 Why keep per-task status inside `WritingExam`?

**Why:** the shell renders a full-screen `"Analyzing performance..."` overlay whenever
its `status` is `"evaluating"`. Letting Task 1 reach that state would put a blocking
spinner over an exam in progress — the exact thing the AC forbids.
**Alternative rejected:** a shell-level `writingStatus` — more prop drilling and one
refactor away from re-triggering the overlay.
**Reused:** nothing needed changing; the shell's overlay is untouched and simply never
reached.

### 11.5 Why change backend code on a frontend ticket? (×2)

**The `evaluations` field (§3.8):** AC #14 was unreachable — the data existed on the
server, was persisted, and was discarded on the way out; `GET /result` 404s until both
tasks exist. One additive key was the smallest possible fix. Alternatives (a new
endpoint; relaxing `_get_writing_result`) were larger and riskier.

**The contract fix (§3.7/§8.4):** not optional. Without it *every* writing submit
returns 500 and the ticket cannot function at all. It was found by reading both
schemas and **proven by executing the validation**, not assumed.

**Rule followed:** fix what blocks the deliverable at its true source; file what
doesn't (§8.1, §8.2, §8.5 were filed, not fixed).

### 11.6 Why export the colours instead of defining them locally?

**Why:** `essay-highlighter.tsx` already contains exactly the four AC colours. A second
palette would drift, and the whole value of colour coding is one consistent vocabulary.
**Alternative rejected:** a new `lib/criterion-colours.ts` — better long-term, but it
would mean editing GOA-043's component to import from it, a larger change to a
unit-tested file for no behavioural gain. Worth doing when a third consumer appears.
**Rule followed:** reuse over redefinition; minimal edits to tested code.

### 11.7 Why is the overall band never recomputed client-side?

**Why:** the exam service applies the marking rule and persists the result. A second
implementation would eventually drift and show a candidate arithmetic that does not add
up. The formula string *explains* the number; it does not produce it.
**Verified:** `(6.5 + 2×7.0)/3 = 6.833 → 7.0`, matching the ticket example exactly.
**Discussion point:** the displayed `6.8` is the unrounded weighted mean and `7.0` is
the rounded band — that is what the ticket asks for, and it is genuinely informative
(it shows the rounding).

### 11.8 Why `unoptimized` on `next/image`?

**Why:** pre-signed S3 URLs expire and carry per-request credentials in the query
string. Next's optimizer would cache a URL that stops working and key that cache on a
signature that changes every request.
**Alternative rejected:** `images.remotePatterns` — requires guessing an S3 hostname
nobody has provisioned, and is semantically wrong for expiring URLs anyway.

### 11.9 Why build the stimulus UI at all if the data doesn't exist?

**Why:** the frontend work is the ticket. The image is read from a nullable field, so
the UI degrades to prompt-only today and lights up with **zero frontend changes** once
the backend field ships. The behaviour is proven by an E2E test against a mocked
payload — the same technique `reading-exam.spec.ts` established.
**Alternative rejected:** skipping it and reopening the ticket later — the work would
be identical, just later and with the context lost.

### 11.10 Why delete an existing E2E test?

**Why:** it asserted `textarea.nth(1)`, which tabs make unexpressible — *and* it was
already failing on `dev` because nothing stubbed the session load, so it was running
against a redirect page with no textarea. It was proving nothing.
**Alternative rejected:** rewriting it in place — the same guarantee is now covered
properly in `writing-exam.spec.ts`; keeping a duplicate in an unmocked file would
re-introduce a false failure. A comment in its place records the reasoning.

### 11.11 Why a separate `normalizeWritingTasks.ts`?

**Why:** two real payload shapes exist and the old code assumed one positionally.
Normalisation is its own concern, and `lib/normalizeReadingQuestions.ts` is the
established precedent.
**Alternative rejected:** folding it into `writing-exam.ts` — that file is the rules;
this is shape-wrangling. Keeping them apart keeps both readable.

### 11.12 Component count: five, not six

The earlier plan proposed six new components. `WordCounter` was **not** extracted — it
is ~10 lines of JSX rendered in exactly one place, and the part worth sharing (the
counting and threshold logic) already lives in `lib/writing-exam.ts`. `WritingTaskPanel`
*was* extracted, because it is a genuine boundary that keeps `WritingExam` as pure
orchestration. Extraction is cheap after the fact; premature extraction costs
indirection permanently.

---

## 12. Final status

## ⚠ Partially Complete

**24 of 25 acceptance criteria fully implemented, tested and passing.** One criterion
(AC #2, the Academic Task 1 stimulus image) is **frontend-complete but blocked on
backend, data and infrastructure work outside this ticket's service boundary.**

### What is fully done

- All UI: tabs, stimulus panel, plain textarea, live word counter with orange/green
  thresholds, per-task under-minimum warning with the exact wording, recommended-time
  indicator, per-task submit, collapsed-by-default expandable result card with band and
  top issue per criterion, inline colour-coded highlighting reusing GOA-043, combined
  results with side-by-side tasks and the explicit 33/67 formula.
- Task 2 remains editable throughout Task 1 evaluation, with no blocking spinner —
  asserted directly in E2E.
- 27 new unit tests, 9 new E2E tests, 7 new backend contract tests. All passing.
- `tsc` clean, `next build` clean, 233 exam-service tests passing.
- **A hard blocker fixed:** the Exam↔Writing response contract mismatch (§8.4) that
  made *every* writing submit fail with a 500.

### What still depends on other services

| Blocker | Owner | Blocks |
|---|---|---|
| **§8.1** Stimulus images: ingest → S3 → pre-sign → expose `stimulus_image_url` → seed | Backend + data | AC #2 (image renders; frontend needs no change) |
| **§8.2** `_resolve_task_context` crashes on list-shaped questions | Backend (exam) | **All** writing submits against real seeded data |
| **§8.3** Academic Task 1 hard-fails without a stimulus key | Backend (writing) | Academic writing end-to-end (resolved by §8.1) |
| **§8.5** Gateway's 10s timeout on exam routes vs 10–30s LLM evaluation | Gateway | Intermittent 502s on any real evaluation |
| **§8.6** `/api/profile/update-scores` does not exist | Frontend BFF / user service | Band-score sync to the profile (pre-existing, affects Reading too) |

### Recommended follow-up tickets

1. **`GOA-XXX` — Writing stimulus image pipeline** (§8.1) — P1, unblocks AC #2.
2. **`BUG-XXX` — `_resolve_task_context` crashes on real writing questions** (§8.2) —
   P1, one-function fix; port the logic from `lib/normalizeWritingTasks.ts`.
3. **`BUG-XXX` — Gateway exam routes need an LLM-appropriate timeout** (§8.5) — P2,
   one line.
4. **`BUG-XXX` — `/api/profile/update-scores` missing** (§8.6) — P2, pre-existing.
5. **`CHORE-XXX` — Rewrite unmocked `exam-flow.spec.ts` tests** (§8.10) — P3.

### Bottom line

Everything within `Service: Frontend` is delivered and verified. The Writing exam UI is
complete and functional end-to-end against the API contract as it stands. Two backend
defects that would have made the feature fail at runtime were found by inspection and
proven by execution — one was fixed here because it blocked the deliverable outright,
the other is filed with a ready-made fix. Academic Task 1 will show its chart the
moment the backend supplies a URL; no further frontend work is required for that.

---

# 13. Revision 2 — postponed images + the 500 fix

Two follow-up items were raised after the initial delivery. Both are complete.

---

## 13.1 Academic Task 1 stimulus image — postponed

### The decision

The original requirement included an Academic Task 1 stimulus image (S3 pre-signed
URL plus vision context for evaluation). **The team has postponed it**: the Writing
agents were changed and the current pipeline no longer supports image-based
evaluation. This is a scope decision, not a defect.

### Why it mattered more than "the image is missing"

The *requirement* of an image was actively breaking Academic Writing — the writing
service refused to evaluate Academic Task 1 without one. See §13.2.3.

### What was changed

| File | Change |
|---|---|
| `lib/normalizeWritingTasks.ts` | Removed `stimulusImageUrl` from `NormalizedWritingTask` and deleted the `readStimulusUrl` reader. The normaliser now reads **no image field of any kind**. A `TODO(GOA-058 follow-up)` on the interface states exactly what to add back and where. |
| `components/writing/StimulusPanel.tsx` | Removed `next/image`, the zoom button, the zoom modal, the Escape handler and the `zoomed` state. The component is now purely presentational. A 20-line `TODO` block documents the three-step path to reinstating images. |
| `services/exam/app/services/session_service.py` | `_resolve_task_context` no longer reads `image_s3_key`; it returns `stimulus_s3_key = None` with a TODO showing the one line that restores it. The `(prompt, stimulus_s3_key)` tuple shape is unchanged. |
| `services/writing/app/evaluation.py` | **Removed the `EvaluationFailed("Academic Task 1 requires a stimulus image.")` guard.** See §13.2.3. |
| `test/unit/writing-exam.test.ts` | Stimulus assertions replaced with one proving a stray image field on the payload is **ignored**. |
| `test/e2e/writing-exam.spec.ts` | Image/zoom tests replaced with "Academic Task 1 shows the prompt and no image", plus a test that a payload carrying a legacy image field stays fully usable. |
| `services/writing/tests/unit/test_vision.py` | `test_academic_task1_fails_without_image` becomes `test_academic_task1_without_image_evaluates_without_chart_context`, asserting all four criteria evaluate with `chart_context=None`. |

### Requirements checklist

| Requirement | Status | How |
|---|---|---|
| Keep the frontend fully functional without images | Yes | 10/10 writing E2E tests pass; Academic and General Training both render and submit |
| Do not expect or require `image` / `image_key` / `stimulus_image_url` | Yes | No frontend code reads any of them; a stray field is ignored (unit + E2E test) |
| If an image is absent, render only the prompt | Yes | `StimulusPanel` renders prompt and instructions only |
| Remove assumptions that Academic Task 1 has an image | Yes | Removed in the frontend, the exam service **and** the writing-service guard |
| Structured so image support returns without major refactoring | Yes | `StimulusPanel` keeps its `examType` prop and Academic/GT branch; the exam-to-writing `stimulusS3Key` plumbing is untouched and still optional |
| Clear TODO comments where support is reintroduced | Yes | Five `TODO(GOA-058 follow-up)` blocks: interface, panel, exam service, writing service, E2E spec |
| Do not break the current API contract | Yes | No request or response field added, removed or renamed. `ExamTaskEvaluationRequest.stimulusS3Key` remains an accepted optional field |

**Reinstating images later is additive:** add `stimulusImageUrl` to the interface,
populate it in the normaliser, render it in `StimulusPanel`, return the key from
`_resolve_task_context`, and restore the writing-service guard. No component tree,
prop or endpoint changes are required.

---

## 13.2 The HTTP 500 on writing submission — fixed

### 13.2.1 Root cause

**`AttributeError: 'list' object has no attribute 'get'` at
`services/exam/app/services/session_service.py:652`, inside `_resolve_task_context`.**

```python
questions_data = self._decode_json(question["questions"])
task_key = "task1" if task_number == 1 else "task2"
task_data = (questions_data or {}).get(task_key, {})   # <-- raises on a list
```

The method assumed `questions` is a **dict** keyed `task1`/`task2`. Every question
produced by real ingestion (`app/ingestion/writing_parser.py`) is a **list** of
`{number, prompt, question_type, instructions}`. A non-empty list is truthy, so
`questions_data or {}` left it a list and `.get` raised.

Nothing catches `AttributeError` — not the `try/except WritingServiceError` in
`_submit_writing`, not the router — so FastAPI returned a bare
**HTTP 500 "Internal Server Error"** for **both** tasks, exactly matching the
reported symptom.

**Reproduced before changing anything**, using the real parsed fixture from
`data/parsed/IELTS14/writing/test1.json`:

```
create: 200
submit task 1: HTTP 500     body: Internal Server Error
submit task 2: HTTP 500     body: Internal Server Error
```

and with exceptions surfaced rather than swallowed by the test client:

```
app/services/session_service.py:579: in _submit_writing
    task_prompt, stimulus_s3_key = await self._resolve_task_context(...)
>       task_data = (questions_data or {}).get(task_key, {})
E       AttributeError: 'list' object has no attribute 'get'
app/services/session_service.py:652: AttributeError
```

### 13.2.2 The full flow, traced

Every layer was checked rather than assumed. Two of them had defects.

| Layer | Verdict |
|---|---|
| **Frontend payload** | OK. `submitWritingTask` sends `{ answers: {}, task_number, essay_text }` — top level, as the schema requires. |
| **Gateway forwarding** | Routing correct (`server.go:115`). Its 10s client is still shorter than the work it proxies — see §8.5, unchanged and still open. |
| **Exam service validation** | OK. `SubmitAnswersRequest` accepts the payload; the 400 guard for missing `task_number`/`essay_text` behaves correctly. |
| **Exam service task resolution** | **DEFECT — the root cause.** `_resolve_task_context` crashed on list-shaped questions. |
| **Database writes** | OK. `save_response` UPSERTs before evaluation, `save_evaluation` updates after. The crash happened *after* the response row was written, so no candidate text was lost even when the request 500'd. |
| **Writing service response schema** | **DEFECT (fixed in revision 1).** The exam client modelled `highlighted_issues: [{issue, start, end}]`; the service emits `inline_issues: [{issue_type, start_char, end_char}]`. |
| **Pydantic validation and (de)serialisation** | Same defect: `ValidationError` escaped the retry loop (which catches only HTTP/timeout/network) and `_submit_writing` (which catches only `WritingServiceError`), producing a second unhandled 500. |
| **Response mapping** | OK once the schema matched. |
| **Exception handling** | Two gaps, both closed: `AttributeError` was reachable at all (root cause removed), and `ValidationError` had no handler (now a clean 502). |

**The two bugs are independent and sequential.** The `AttributeError` fires first and
is what users hit today; the schema mismatch fires immediately after it is fixed.
Both are now fixed. Neither is masked.

### 13.2.3 A third blocker found on the way

With the `AttributeError` fixed, Academic Task 1 still failed — with **502** this
time, from `evaluation.py:173`:

```python
if is_academic_task1 and not stimulus_s3_key:
    raise EvaluationFailed("Academic Task 1 requires a stimulus image.")
```

Since no ingested question carries an image key, this guard **rejected every real
Academic Task 1 submission** — the single most common writing exam. Removing it is
required by the image postponement (§13.1) and is safe: `chart_context` was already
optional in the agent prompt (`agents.py:325`, `if chart_context:`), so the agents
simply run without the chart-context block.

### 13.2.4 Files changed in revision 2

| File | Change |
|---|---|
| `services/exam/app/services/session_service.py` | `_resolve_task_context` rewritten to handle both shapes via the existing `_question_list` normaliser; selects by declared `number` with positional fallback; returns `stimulus_s3_key = None` with a TODO. **The root-cause fix.** |
| `services/writing/app/evaluation.py` | Removed the Academic-Task-1-requires-an-image guard; TODO documents restoring it. |
| `services/exam/tests/test_e2e_exam.py` | Added `_writing_question_ingested_list_shape()` fixture plus 4 regression tests. |
| `services/writing/tests/unit/test_vision.py` | Guard test inverted to assert evaluation succeeds without an image. |
| `services/frontend/lib/normalizeWritingTasks.ts` | Image field removed; TODO added. |
| `services/frontend/components/writing/StimulusPanel.tsx` | Image and zoom removed; TODO added. |
| `services/frontend/test/unit/writing-exam.test.ts` | Stimulus tests replaced with "ignores stray image field". |
| `services/frontend/test/e2e/writing-exam.spec.ts` | Image/zoom tests replaced with prompt-only plus stray-field resilience. |

### 13.2.5 Why the bug happened

Three causes compounded, and the third is the instructive one:

1. **Two data shapes, one assumption.** `questions` is schemaless JSONB. Ingestion
   writes a list; seed and fixture data write a dict. `_resolve_task_context` was
   written against the dict and never met the list.

2. **`x or {}` is not a type guard.** It reads defensively but only guards
   *falsiness*. A non-empty list sails straight through — the idiom gave the
   appearance of safety while providing none.

3. **The tests encoded the same assumption as the code.** Every writing fixture used
   the dict shape, so the suite was green while the feature was completely broken in
   production. The identical failure mode caused the schema mismatch: that fixture
   used the *consumer's* invented field names for both sides of a contract.

> **The lesson for this codebase:** a fixture that invents its own data shape tests
> only that the code agrees with itself. Fixtures for a service boundary must be
> pinned to the **producer** — real ingestion output, or the upstream service's own
> schema.

### 13.2.6 Why the fix is correct

- **It removes the crash rather than catching it.** No `try/except AttributeError`,
  no bare `except`, no silent fallback. The method now genuinely understands both
  shapes, so there is no exception left to swallow.
- **It reuses the existing normaliser.** `self._question_list(...)` is the same
  helper `_public_question` uses, so the submit path and the read path can no longer
  disagree about what a question contains — this class of bug cannot recur between
  those two methods.
- **It is correct, not merely non-crashing.** The regression test asserts the **right
  prompt reaches the Writing service** for each task. Returning 200 with a `None`
  prompt would have been a silent regression dressed up as a fix.
- **Task order comes from data, not position.** The declared `number` wins, with
  index as fallback, so a re-ordered array cannot swap Task 1 and Task 2.
- **Backward compatible.** The dict shape still works — every pre-existing writing
  test passes unchanged. The `highlighted_issues` spelling also still validates via
  `AliasChoices`.
- **Failures degrade honestly.** An unreadable upstream body raises
  `WritingServiceError` and becomes a **502 (upstream failure)** instead of a 500 that
  blamed the exam service for the writing service's payload.
- **No API contract change.** No field added, removed or renamed on any request or
  response.

### 13.2.7 Test results

**New regression tests (exam service):**

| Test | Asserts |
|---|---|
| `test_writing_submit_succeeds_on_ingested_list_shape[1]` | Task 1 on real-shaped data returns **200**, correct prompt forwarded |
| `test_writing_submit_succeeds_on_ingested_list_shape[2]` | Task 2 on real-shaped data returns **200**, correct prompt forwarded |
| `test_writing_full_flow_on_ingested_shape_produces_weighted_band` | Task 1 gives `task_submitted`; Task 2 gives `submitted`; result gives **band 7.0** |
| `test_academic_task1_sends_no_stimulus_key` | Academic Task 1 submits successfully with no stimulus key |

Parametrised over both tasks specifically because the report was *"submitting either
Task 1 or Task 2 returns Internal Server Error"*.

**Full suite results after revision 2:**

| Suite | Command | Result |
|---|---|---|
| Exam service | `python -m pytest -q` | **237 passed**, 3 skipped *(was 233 — plus 4 regression tests)* |
| Frontend unit | `npx vitest run` | **44 passed** (4 files) |
| Frontend types | `npx tsc --noEmit` | clean |
| Frontend build | `npx next build` | Compiled successfully, TypeScript clean |
| Writing E2E | `npx playwright test test/e2e/writing-exam.spec.ts` | **10 passed** *(was 9 — plus the stray-field test)* |
| E2E regression | `writing-exam + reading-exam` | **15 passed** |

**Before and after, on the exact reported scenario:**

```
BEFORE   create: 200 · submit task 1: HTTP 500 · submit task 2: HTTP 500
AFTER    create: 200 · submit task 1: HTTP 200 · submit task 2: HTTP 200
                       -> GET result: HTTP 200, overall_band 7.0
```

**Not runnable in this environment (pre-existing, unrelated):**
`services/writing/tests/unit/` fails to import `anthropic` and `docx`
(`ModuleNotFoundError`) because those packages are not installed locally. The updated
`test_vision.py` is written for CI, where they are present.

### 13.2.8 Backend issues — status after revision 2

| Ref | Issue | Status |
|---|---|---|
| §8.1 | No stimulus image pipeline | **No longer a blocker** — image support formally postponed (§13.1) |
| §8.2 | `_resolve_task_context` crashes on list-shaped data | **FIXED** — this was the 500 |
| §8.3 | Academic Task 1 hard-fails without a stimulus key | **FIXED** — guard removed |
| §8.4 | Exam-to-Writing response contract mismatch | **FIXED** (revision 1) |
| §8.5 | Gateway 10s timeout on exam routes | **STILL OPEN** — should fix; will cause intermittent 502s under real LLM latency |
| §8.6 | `/api/profile/update-scores` missing | **STILL OPEN** — pre-existing, affects Reading too |
| §8.7 to §8.11 | Docs drift, hardcoded userId, criterion naming, unmocked tests, missing test deps | Nice to have, unchanged |

**§8.5 is now the highest-priority remaining backend item.** With the 500s gone, it is
the one thing left that can still fail a real submission: four parallel LLM calls
routinely exceed the Gateway's 10-second window while the exam service is still
waiting (its own client allows 30s across 2 attempts). The fix is one line in
`services/gateway/server.go:48`.

---

## 13.3 Revised final status

### Complete for the agreed scope

- **24 of 25 original acceptance criteria implemented and tested.** AC #2 (Academic
  Task 1 stimulus image) is **formally postponed by team decision** — it is no longer
  in scope, and the code is structured plus commented so it returns additively.
- **Writing submission works end to end.** Both Task 1 and Task 2 return 200, the
  combined weighted band is produced, and the frontend receives real evaluation
  responses instead of HTTP 500.
- **Three backend defects fixed at root cause**, none masked: the list/dict crash, the
  Exam-to-Writing schema mismatch, and the stimulus-image guard.
- **All suites green:** 237 exam-service tests, 44 frontend unit tests, 10 writing
  E2E, 15 E2E overall, clean `tsc`, clean build.

### One item still open before production

**§8.5 — the Gateway's 10-second timeout on exam routes.** Not introduced by this work
and not fixable within the frontend service boundary, but it will produce intermittent
502s on real LLM-backed submissions until it is raised. One line, recommended as the
immediate next ticket.

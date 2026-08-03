# GOA-058 Onboarding — The Writing Exam, End to End

> **Audience:** a developer who has never opened this repo before and is about to
> implement GOA-058.
> **Goal:** understand *why* every piece exists before writing a single line.
> **Status:** nothing has been implemented yet. This is a teaching document plus a
> design review.

Everything in here was read out of the repo at commit `31f71ff` (branch `dev`).
Where I say "this is broken", I cite the file and line so you can verify it yourself
rather than take my word for it. **Do that.** A senior engineer's claim is a
hypothesis until you've read the code.

---

# Table of Contents

1. [Step 1 — The whole system](#step-1--the-whole-system)
2. [Step 2 — The Writing Exam feature, end to end](#step-2--the-writing-exam-feature-end-to-end)
3. [Step 3 — File-by-file walkthrough](#step-3--file-by-file-walkthrough)
4. [Step 4 — The three dependency tickets](#step-4--the-three-dependency-tickets)
5. [Step 5 — Every acceptance criterion analysed](#step-5--every-acceptance-criterion-analysed)
6. [Step 6 — Review of the proposed implementation plan](#step-6--review-of-the-proposed-implementation-plan)
7. [Step 7 — The mental model](#step-7--the-mental-model)
8. [Step 8 — Before you write code](#step-8--before-you-write-code)

---

# Step 1 — The whole system

## 1.1 What this product is

GOA is an IELTS preparation platform. A student can practise conversationally
(chat), practise speaking (audio), and sit **simulated exams** in the four IELTS
skills: Reading, Listening, Writing, Speaking.

Two of those skills are *objectively* markable (Reading, Listening — there is an
answer key). Two require *judgement* (Writing, Speaking — a human examiner, or in
our case an LLM, assigns band scores against a rubric). **This distinction is the
single most important architectural fact in the codebase.** It explains why the
Writing exam does not look like the Reading exam, why there are two services
involved instead of one, and why the submit endpoint behaves differently for
writing than for everything else.

Hold on to that. We'll come back to it repeatedly.

## 1.2 Top-level repository layout

```
GOA2/
└── GOA/                       <- the actual git repo root (note the nesting!)
    ├── apps/web/              <- EMPTY. A stub. Ignore it entirely.
    ├── docs/                  <- architecture notes, ADRs, ticket docs (you are here)
    ├── evals/                 <- LLM evaluation harness + seed data
    ├── infra/                 <- docker, postgres init
    ├── monitoring/            <- prometheus/grafana config
    ├── packages/contracts/    <- shared type contracts
    └── services/
        ├── frontend/          <- Next.js 16 app. THIS IS WHERE YOU LIVE.
        ├── gateway/           <- Go / Fiber. The single front door.
        ├── exam/              <- Python / FastAPI. Exam sessions, timers, grading.
        ├── writing/           <- Python / FastAPI. LLM essay evaluation.
        ├── speaking/          <- Go. Audio streaming + transcription.
        ├── orchestration/     <- Python / FastAPI. Chat intent routing, SSE.
        ├── rag/               <- Python / FastAPI + pgvector. Retrieval.
        ├── user/              <- TypeScript / NestJS. Auth, profiles.
        ├── ingestion/         <- Python worker. Cambridge IELTS book ingestion.
        └── notification/      <- Node. Email dispatch.
```

**First gotcha to internalise:** the git repo root is `GOA2/GOA`, not `GOA2`. If you
run `git status` from `GOA2` you get `fatal: not a git repository`. And
`apps/web/` is an empty stub with a lone `.gitkeep` — the real frontend is
`services/frontend`. Both of these have cost people an hour before.

**Second gotcha:** [`docs/architecture.md`](architecture.md) claims the Exam service is
"TypeScript / NestJS". It is not — it is Python/FastAPI
([`services/exam/app/api/sessions.py`](../services/exam/app/api/sessions.py) is FastAPI).
The doc drifted. This is a healthy lesson: **in this repo, code is the source of
truth and docs are a hint.** I verified every claim in this document against the
code for exactly that reason.

## 1.3 System topology

```
                            ┌──────────────────────────┐
                            │  Browser (Next.js app)   │
                            │  localhost:3000          │
                            └────────────┬─────────────┘
                                         │  HTTPS/REST + SSE + WebSocket
                                         │  credentials: "include"  (HttpOnly cookies)
                                         ▼
                        ╔════════════════════════════════════╗
                        ║   GATEWAY  (Go / Fiber)  :8080     ║
                        ║  ─────────────────────────────     ║
                        ║  CORS · JWT · rate limit           ║
                        ║  correlation IDs · INTERNAL_API_KEY║
                        ╚═══╤════════╤═════════╤═════════╤═══╝
                            │        │         │         │
              ┌─────────────┘        │         │         └──────────────┐
              ▼                      ▼         ▼                        ▼
     ┌─────────────────┐   ┌──────────────┐  ┌─────────────┐   ┌────────────────┐
     │  EXAM  (FastAPI)│   │ WRITING      │  │ ORCHESTR.   │   │ USER (NestJS)  │
     │  sessions,      │   │ (FastAPI)    │  │ chat/SSE    │   │ auth, profile  │
     │  timers, grading│──▶│ LLM eval     │  │ :8083       │   │ :8081          │
     │                 │   │ :8000        │  └─────────────┘   └────────────────┘
     └────────┬────────┘   └──────┬───────┘
              │                   │
              │                   ├──▶ Anthropic API (4 criterion agents)
              │                   └──▶ S3 / LocalStack (stimulus images)
              ▼                   ▼
     ┌──────────────────────────────────────┐
     │      PostgreSQL (logical DBs)        │
     │  exam_db · writing_db · user_db · …  │
     └──────────────────────────────────────┘
```

Note the arrow that matters most for you:
**Exam ──▶ Writing.** The browser never talks to the Writing service during an exam.
The Exam service calls it server-to-server. We'll dissect why in §1.6.

## 1.4 The Gateway — what it is for

Read [`services/gateway/server.go`](../services/gateway/server.go). It is short and
the comments are unusually good — whoever wrote them documented the *bugs that
forced each decision*, which is the most valuable kind of comment.

The Gateway owns five concerns:

| Concern | Why | Evidence |
|---|---|---|
| **CORS** | Browser preflight got 405 and *every* call failed with `net::ERR_FAILED`. Wildcard origin is illegal with `AllowCredentials`, so there's an explicit allow-list. | `server.go:60-75` (BUG-043) |
| **JWT auth** | `api := app.Group("/api", middleware.JWT(...))` — everything under `/api` is authenticated, with a Redis blacklist for logout. | `server.go:92` |
| **Rate limiting** | 60 req/window, Redis-backed. | `server.go:93` |
| **Secret custody** | `INTERNAL_API_KEY` stays server-side. | see below |
| **Timeout tiering** | Shared client is 10s; streaming/LLM client is 5 min. | `server.go:46-58` |

### The secret-custody point — internalise this one

`server.go:105-110`:

> exam and writing were called directly on their service ports with
> `INTERNAL_API_KEY` published to the browser in a `NEXT_PUBLIC_` variable (BUG-046).

Any `NEXT_PUBLIC_*` variable is **inlined into the client JavaScript bundle** and
served to every visitor. The exam service protects its endpoints with
`validate_internal_api_key` ([`sessions.py:21`](../services/exam/app/api/sessions.py#L21)) —
so shipping that key to the browser dissolved the entire boundary it existed to
enforce. BUG-046 moved everything behind the Gateway, which holds the key
server-side.

Consequence for you: **never add a `NEXT_PUBLIC_` variable containing a secret, and
never call `http://localhost:8085` (exam) or `:8000` (writing) from browser code.**
Everything goes through `http://localhost:8080/api/…`.

### Timeout tiering — why it exists

`server.go:49-54`:

> Streaming paths need their own client: the shared one has a 10s timeout, which
> would sever a chat or essay-evaluation stream mid-flight. A speaking evaluation
> alone has been measured at ~77s.

And from the GOA-087 commit message (`0cfd6bd`), a beautiful debugging story:

> CV review returned 502 at exactly 10.007s while the writing service was still
> working — **a gateway timeout wearing an upstream failure's costume.**

**This matters directly to GOA-058.** A writing exam submit triggers four parallel
LLM calls. Look at which client handles it:

```go
examHandler := handlers.NewExamHandler(httpClient, ...)   // httpClient = 10s !!
```

`server.go:48` — the exam handler uses the **10-second** client. A Task 1 submit
that takes longer than 10s at the Gateway will return 502 even though the exam and
writing services are still happily working. Put that in your pocket; it's in the
risk register in Step 8.

## 1.5 The Exam service

`services/exam/` — Python/FastAPI, asyncpg, layered:

```
app/
├── api/            <- FastAPI routers (thin: HTTP in, HTTP out)
│   ├── sessions.py     generic session lifecycle  ← the one you care about
│   ├── reading.py      reading-specific submit
│   └── listening.py    listening-specific start/submit
├── services/       <- business logic
│   ├── session_service.py       ← the brain. 680 lines. Read it.
│   ├── grading_service.py       answer-key grading (reading/listening)
│   ├── timer_service.py         started_at + limit → remaining
│   ├── writing_client.py        HTTP client → writing service
│   └── audio_delivery_service.py  S3 pre-signing for listening audio
├── repositories/   <- SQL. asyncpg, raw queries.
│   ├── session_repository.py
│   ├── question_repository.py
│   ├── result_repository.py
│   └── writing_response_repository.py   ← writing exam persistence
├── schemas/        <- Pydantic request/response models
├── migrations/     <- .sql files
└── ingestion/      <- Cambridge book parsers (reading/listening/writing/speaking)
```

Responsibilities:

- **Owns the session.** Who is sitting what, when they started, how long is left,
  what state it's in (`in_progress` → `submitted` → `scored`, or `abandoned`).
- **Owns the questions.** Ingested from Cambridge IELTS books, stored as JSONB.
- **Owns objective grading** for Reading/Listening (answer-key comparison).
- **Delegates subjective grading** for Writing to the Writing service.
- **Owns the weighted combination** of Task 1 and Task 2 into a final band.

## 1.6 The Writing service

`services/writing/` — Python/FastAPI, SQLAlchemy. Its job is to turn an essay into
four criterion band scores plus inline issues, using an LLM.

The core design is a **four-agent swarm**
([`app/agents.py`](../services/writing/app/agents.py),
[`app/evaluation.py`](../services/writing/app/evaluation.py)):

```
                      essay text
                          │
        ┌─────────┬───────┴───────┬─────────┐    asyncio.gather — all four in parallel
        ▼         ▼               ▼         ▼
  task_response  cohesion    vocabulary   grammar      (4 separate LLM calls)
        │         │               │         │
        └─────────┴───────┬───────┴─────────┘
                          ▼
              calculate_overall_band()
              mean of 4, rounded to nearest 0.5 (ROUND_HALF_UP)
                          ▼
              EvaluationSummary { evaluations[], overall_band, tokens, cost }
```

Why four separate agents instead of one prompt asking for all four scores?
Because IELTS criteria are **independent rubrics**. Asking one model call to score
all four invites anchoring — a weak grammar impression drags down the vocabulary
score. Separate calls with criterion-specific system prompts
(`CRITERION_PROMPTS`, `agents.py:29`) keep them independent, and they run
concurrently so latency is max(4) not sum(4).

`evaluation.py:213-218` — **any one agent failing fails the whole evaluation**:

```python
if failures:
    raise EvaluationFailed(f"{len(failures)} of 4 writing agents failed: ...")
```

That's deliberate. A 3-of-4 mean presented as an "overall band" would be a
confident lie — the same class of defect BUG-040 flagged.

### How inline issues get their character offsets

This is the mechanism GOA-043's highlighter depends on, so understand it properly.

The agent is instructed (`agents.py:105-109`):

> Every issue text must be an **exact, case-sensitive substring** of the essay so
> character offsets can be computed.

Then `_annotate_issues` (`agents.py:158-172`) does:

```python
start = essay_text.find(item.text)
if start < 0:
    continue                      # silently drop issues that don't match
annotated.append(InlineIssue(
    text=..., issue_type=..., suggestion=...,
    start_char=start, end_char=start + len(item.text),
))
```

So offsets are computed **server-side by substring search**, not by the model. The
model only has to quote the essay accurately. Issues it hallucinates (that don't
appear verbatim) are silently dropped. This is a nice defensive design — but note
the consequence: **the offsets are valid only against the exact essay text that was
submitted.** If the frontend renders highlights over a *different* string (say, a
trimmed or normalised version), every highlight lands in the wrong place. Keep the
submitted text verbatim.

### The Writing service's public surface

| Endpoint | Used by | Purpose |
|---|---|---|
| `POST /essays` | Orchestration | Create essay record |
| `POST /essays/evaluate` | (chat path, non-streaming) | Evaluate typed essay |
| `POST /essays/{id}/evaluate` | Gateway → SSE → chat UI | **Streaming** evaluation |
| `POST /essays/evaluate/exam` | **Exam service (server-to-server)** | Exam task evaluation |
| `POST /cv/*` | Gateway | CV upload/review |

**The one you care about is `/essays/evaluate/exam`**
([`routers/essays.py:310-371`](../services/writing/app/routers/essays.py#L310-L371)).
Note that it is **not routed by the Gateway**. It is called only by the Exam
service via `writing_client.py`. That is intentional: the exam flow must persist
the response *before* evaluating, must attribute the evaluation to a session and
task number, and must not let the browser fabricate an evaluation for a session it
doesn't own.

### Caching

`evaluation_cache_key(essayText, "exam", examType, settings)` — identical essays
replay a cached evaluation instead of paying for four LLM calls
(`essays.py:319-325`, `find_cached_evaluation`). The response carries
`from_cache: bool`. Relevant to you only in that **E2E tests that reuse the same
essay text may get suspiciously fast responses.** Not a bug.

## 1.7 The frontend

`services/frontend/` — Next.js 16.2.9, React 19.2.4, App Router, Tailwind,
TypeScript, `reactCompiler: true`.

```
services/frontend/
├── app/                        <- App Router: routes are folders
│   ├── page.tsx                    landing
│   ├── layout.tsx
│   ├── globals.css
│   ├── login/ register/ reset-password/ onboarding/ profile/
│   ├── chat/                       conversational practice
│   ├── speaking/                   speaking practice + history
│   ├── exam/
│   │   ├── page.tsx                exam prep: type toggle + skill cards   [GOA-054]
│   │   ├── shell/page.tsx          THE EXAM SHELL — timer, header, skill switch
│   │   └── results/page.tsx        results page (Reading branch + generic)
│   ├── api/                        Next.js server routes (BFF)
│   │   └── chat/…                  ONLY chat routes exist here
│   ├── hooks/                      shared React hooks
│   │   ├── useExamTimer.ts             ← you will use this
│   │   ├── usePassageHighlights.ts
│   │   ├── useAudioVisualizer.ts
│   │   └── useSession*.ts
│   └── types/                      shared TS types
│       ├── exam.ts                     ← ExamType, SkillArea, WritingStatus
│       ├── reading.ts
│       └── speaking.ts
├── components/
│   ├── ui/                         Sidebar, Skeleton
│   ├── auth/  landing/  onboarding/
│   ├── chat/                       chat + THE WRITING PRACTICE UI  [GOA-043]
│   │   ├── essay-composer.tsx
│   │   ├── essay-highlighter.tsx       ← REUSE THIS
│   │   └── writing-evaluation-panel.tsx ← REUSE ITS COLOUR MAPS
│   ├── reading/                    THE READING EXAM UI  [GOA-055]  ← your template
│   └── speaking/
├── lib/                            <- API clients + pure logic
│   ├── exam-api.ts                     ← you will extend this
│   ├── reading-api.ts
│   ├── writing-api.ts                  chat-path writing client
│   ├── writing-stream.ts               SSE parser for chat path
│   ├── reading-grading.ts / .test.ts    pure logic + colocated unit test
│   ├── reading-results.ts / .test.ts
│   └── reading-result-storage.ts       sessionStorage carry-forward
└── test/
    ├── unit/                       vitest + jsdom (*.test.ts / *.test.tsx)
    └── e2e/                        playwright (*.spec.ts)
```

### Architectural conventions you must follow

**1. `lib/` holds pure logic and API clients. `components/` holds rendering. `app/`
holds routes and wiring.**
This separation is why `reading-grading.ts` has a colocated `reading-grading.test.ts`
that runs under vitest with no DOM. Pure functions are cheap to test; components
are not. When GOA-058 asks for unit tests of the word counter, that tells you the
word counter belongs in `lib/`, not inside a component.

**2. The API layer is a thin typed wrapper around `fetch`.** There is no
React Query, no SWR, no Redux, no Zustand. Look at
[`lib/exam-api.ts`](../services/frontend/lib/exam-api.ts): a module-level
`API_BASE`, a shared `headers` const, a shared `fetchOptions = { credentials: "include" }`,
and one exported `async function` per endpoint that throws on `!response.ok`.

**Follow this pattern exactly.** Don't introduce a data-fetching library for one
ticket.

**3. State management is local React state.** `useState` + `useEffect` in the page
or top-level feature component, passed down as props.
[`ReadingExam.tsx`](../services/frontend/components/reading/ReadingExam.tsx) uses a
`useReducer` for its answers map because it's genuinely complex; everything else is
`useState`. Cross-page state uses `sessionStorage` (see §1.8).

**4. Test split.** `vitest.config.ts` excludes `**/e2e/**` and `**/*.spec.ts`;
`playwright.config.ts` sets `testDir: "./test/e2e"`. So:

- `*.test.ts` / `*.test.tsx` → **vitest** (unit, jsdom)
- `*.spec.ts` under `test/e2e/` → **playwright** (E2E, real browser)

Both tools default to grabbing `*.spec.ts`, hence the explicit fencing. Name your
files accordingly or they'll run in the wrong runner and fail confusingly.

### State management, drawn

```
  ┌──────────────────────────────────────────────────────────────┐
  │  URL search params        ?session=<uuid>&skill=Writing       │  ← navigation state
  ├──────────────────────────────────────────────────────────────┤
  │  sessionStorage           "active_exam_session"               │  ← resume + handoff
  │                           "reading_result_<id>"               │
  ├──────────────────────────────────────────────────────────────┤
  │  React useState           session, status, drafts, tab        │  ← in-page state
  │  React useReducer         ReadingExam answers map             │
  ├──────────────────────────────────────────────────────────────┤
  │  Server (source of truth) started_at, remaining, evaluations  │  ← durable state
  └──────────────────────────────────────────────────────────────┘
```

The timer is worth calling out. `useExamTimer` seeds from the server's
`remaining_time_seconds` and ticks locally. **The client clock is a display
convenience; the server's `started_at` is the truth**
(`timer_service.is_expired` is re-checked on submit). If the user reloads, the
server tells them the real remaining time. That's the correct design for anything
time-enforced — never trust a client-side countdown.

## 1.8 Existing Writing-related infrastructure (inventory)

This is your reuse inventory. Know what's already here before you build anything.

| Layer | Asset | Location | Reuse for GOA-058? |
|---|---|---|---|
| Backend | 4-agent evaluation swarm | `services/writing/app/agents.py`, `evaluation.py` | ✅ untouched |
| Backend | Exam task endpoint | `writing/app/routers/essays.py:310` | ✅ untouched |
| Backend | Exam→Writing HTTP client | `exam/app/services/writing_client.py` | ✅ untouched |
| Backend | Per-task persistence | `exam/app/repositories/writing_response_repository.py` | ✅ untouched |
| Backend | Per-task submit + weighted result | `exam/app/services/session_service.py:550-683` | ⚠️ one-line addition |
| Frontend | Inline highlighter + tooltips | `components/chat/essay-highlighter.tsx` | ✅ **reuse directly** |
| Frontend | Criterion colour maps | `essay-highlighter.tsx:27-55`, `writing-evaluation-panel.tsx:42-64` | ✅ **reuse** |
| Frontend | Evaluation panel (bars, print) | `components/chat/writing-evaluation-panel.tsx` | ⚠️ chat-shaped; reuse ideas not component |
| Frontend | Chat writing client | `lib/writing-api.ts` | ❌ wrong path for exam |
| Frontend | SSE stream parser | `lib/writing-stream.ts` | ❌ chat only |
| Frontend | Exam session client | `lib/exam-api.ts` | ⚠️ extend |
| Frontend | Exam shell + timer | `app/exam/shell/page.tsx`, `hooks/useExamTimer.ts` | ✅ extend |
| Frontend | Tab pattern | `components/reading/SectionTabs.tsx` | ✅ **copy the pattern** |
| Frontend | E2E mocking pattern | `test/e2e/reading-exam.spec.ts` | ✅ **copy wholesale** |

---

# Step 2 — The Writing Exam feature, end to end

Now forget everything except Writing.

## 2.0 The two writing paths — don't confuse them

There are **two completely separate writing experiences** in this product, and
conflating them is the #1 way to get lost:

```
 PATH A — "Writing Practice" (chat)          PATH B — "Writing Exam"  ← GOA-058
 ────────────────────────────────            ─────────────────────────────
 /chat  →  EssayComposer                     /exam → /exam/shell → /exam/results
    │                                            │
    ▼                                            ▼
 POST /api/chat (SSE)                         POST   /api/exam/sessions
    │  orchestration classifies intent        GET    /api/exam/sessions/:id
    ▼                                         PUT    /api/exam/sessions/:id/submit
 writing_url event → SSE stream               GET    /api/exam/sessions/:id/result
    │                                            │
    ▼  streamWritingEvaluation()                 ▼  (exam service calls writing
 WritingEvaluationPanel                             service server-to-server)
                                              (your new components)

 One essay. No session. No timer.            Two tasks. Session. Timer. Weighting.
 No task numbers. No weighting.              Per-task submit. Penalty flags.
 Streaming, criterion-by-criterion.          Request/response, whole-task.
```

GOA-058 is **Path B only**. Path A is finished (GOA-043) and you should not touch
it — but you *will* borrow its highlighter component.

## 2.1 The user's journey

```
 1. /exam                 "Academic" or "General Training"?  Four skill cards.
 2. click "Take Exam" on the Writing card
 3. /exam/shell?session=<uuid>       60:00 timer starts
 4. Task 1 tab: stimulus (chart image, or letter scenario) + textarea
                live word counter, "Suggested: 20 min"
 5. write ~150 words → submit Task 1
 6. Task 1 tab collapses into a compact result card (band + top issue per criterion)
    ─── evaluation runs; NO blocking spinner ───
 7. user switches to Task 2 tab and keeps writing THE WHOLE TIME
 8. write ~250 words → submit Task 2
 9. /exam/results?session=<uuid>&skill=Writing
10. Combined: Task 1 and Task 2 side by side, big overall band,
    explicit formula "(6.5 × 33%) + (7.0 × 67%) = 6.8 → Band 7.0"
```

Step 6-7 is the whole point of the ticket. In a real IELTS exam you get 60 minutes
for both tasks and you manage your own time. If we blocked the UI for ~30 seconds
while four LLM calls ran, we'd be stealing exam time from the candidate. Hence
**"Task 2 remains fully editable while Task 1 evaluation runs"** and
**"No blocking spinner"**. Those two ACs are not cosmetic; they're the reason the
backend was built with per-task submit in the first place (GOA-053).

## 2.2 Sequence diagram — the complete lifecycle

```
Browser            Next.js page        Gateway :8080      Exam :8085       Writing :8000     Anthropic
   │                    │                    │                 │                 │              │
   │ click "Take Exam"  │                    │                 │                 │              │
   ├───────────────────▶│                    │                 │                 │              │
   │              createSession()             │                 │                 │              │
   │                    ├── POST /api/exam/sessions ──────────▶│                 │              │
   │                    │   {user_id, exam_type, skill_area}   │                 │              │
   │                    │                    │  +X-Internal-Api-Key              │              │
   │                    │                    │                 │ get_random_question()          │
   │                    │                    │                 │ INSERT exam_sessions           │
   │                    │◀── {session_id, first_question_set} ─┤                 │              │
   │  sessionStorage.setItem("active_exam_session")            │                 │              │
   │  router.push(/exam/shell?session=…)     │                 │                 │              │
   │                    │                    │                 │                 │              │
   │  ── ExamShell mounts ──                 │                 │                 │              │
   │                    ├── GET /api/exam/sessions/:id ───────▶│                 │              │
   │                    │◀── {…, remaining_time_seconds, questions[]} ───────────┤              │
   │                    │  useExamTimer(remaining, onTimeUp)   │                 │              │
   │                    │  setInterval heartbeat 60s ─────────▶│ (PATCH heartbeat)              │
   │                    │                    │                 │                 │              │
   │  types Task 1 …    │  local useState, live word count     │                 │              │
   │                    │                    │                 │                 │              │
   │  submit Task 1     │                    │                 │                 │              │
   │                    ├── PUT /api/exam/sessions/:id/submit ▶│                 │              │
   │                    │   {answers:{}, task_number:1, essay_text:"…"}          │              │
   │                    │                    │                 │ word_count = len(split())      │
   │                    │                    │                 │ penalty_flag = wc < 150        │
   │                    │                    │                 │ INSERT exam_writing_responses  │
   │                    │                    │                 │ _resolve_task_context()        │
   │                    │                    │                 ├─ POST /essays/evaluate/exam ──▶│
   │                    │                    │                 │  {essayText, taskNumber,       │
   │                    │                    │                 │   stimulusS3Key, taskPrompt}   │
   │                    │                    │                 │                 ├─ 4 parallel ─▶│
   │                    │                    │                 │                 │◀─ 4 results ──┤
   │                    │                    │                 │◀ {evaluations[], overall_band} │
   │                    │                    │                 │ UPDATE evaluation_result       │
   │                    │◀── {status:"task_submitted", overall_band, word_count, penalty_flag} ─┤
   │  Task 1 → compact card.  Task 2 STILL EDITABLE THROUGHOUT. │                 │              │
   │                    │                    │                 │                 │              │
   │  submit Task 2     ├── PUT …/submit  {task_number:2} ────▶│  … same again … │              │
   │                    │                    │                 │ both tasks present:            │
   │                    │                    │                 │   session.submit() + mark_scored()
   │                    │◀── {status:"submitted", …} ──────────┤                 │              │
   │  router.push(/exam/results?session=…&skill=Writing)       │                 │              │
   │                    ├── GET /api/exam/sessions/:id/result ▶│                 │              │
   │                    │                    │                 │ _get_writing_result()          │
   │                    │                    │                 │ overall = round((t1+2·t2)/3·2)/2│
   │                    │◀── {overall_band, tasks:{1:{…},2:{…}}} ────────────────┤              │
   │  CombinedWritingResults renders formula + side-by-side     │                 │              │
```

## 2.3 Step-by-step, with the nine questions answered

### Step A — "Take Exam" on the Writing card

| Question | Answer |
|---|---|
| **Component** | [`app/exam/page.tsx`](../services/frontend/app/exam/page.tsx), `startExam(skill)` at line 44 |
| **Hook** | None. Plain `useState` (`examType`, `startingExam`) + `useRouter` |
| **API called** | `createSession(userId, examType, skill)` — `lib/exam-api.ts:80` |
| **Endpoint** | `POST http://localhost:8080/api/exam/sessions` → gateway → `POST /sessions` on exam |
| **Service** | Exam. `SessionService.create_session` (`session_service.py:55`) |
| **Data back** | `{ session_id, first_question_set }` |
| **Rendered by** | Nothing — it's a redirect |
| **Stored** | `sessionStorage["active_exam_session"] = {sessionId, examType, skillArea}` then `router.push("/exam/shell?session=…")` |
| **Why** | sessionStorage lets `/exam` detect an in-flight session on mount (`page.tsx:28-34`) and bounce the user straight back into it — refresh-safe resume without a backend "current session" endpoint. Scoped to the tab, cleared on results. |

⚠️ `page.tsx:52` hardcodes `userId = "00000000-0000-0000-0000-000000000001"` with a
`TODO`. Pre-existing; not your ticket.

### Step B — Exam shell mounts

| Question | Answer |
|---|---|
| **Component** | [`app/exam/shell/page.tsx`](../services/frontend/app/exam/shell/page.tsx) → `ExamShellContent` |
| **Hook** | `useSearchParams()` for `?session=`; `useExamTimer(session?.remaining_time_seconds ?? 0, handleTimeUp)` |
| **API** | `getSession(sessionId)` — `exam-api.ts:103` |
| **Endpoint** | `GET /api/exam/sessions/:id` |
| **Service** | Exam. `get_session` + the router's rename `remaining_seconds` → `remaining_time_seconds` (`sessions.py:49`) |
| **Data back** | `ExamSessionResponse` incl. `questions: ExamQuestion[]` |
| **Rendered by** | Header (skill, type badge, timer, submit) + `<main>` that branches on `examConfig.skill` |
| **Stored** | `useState` only |
| **Why Suspense?** | `useSearchParams()` opts the route into CSR; Next requires a Suspense boundary or `next build` fails on static export (`shell/page.tsx:22-25`) |

Three details in this file you must understand before touching it:

1. **The heartbeat** (`shell/page.tsx:107-118`). The backend sweeps silent
   `in_progress` sessions and marks them `abandoned`; submit then 403s and the
   candidate loses the attempt (BUG-054). One immediate beat, then every 60s
   against a 10-minute grace window ⇒ ~9 consecutive failures tolerated.
   `sendHeartbeat` **deliberately never throws** (`exam-api.ts:151-161`) — a
   network blip must not be shown to someone mid-exam.

2. **The `handleTimeUp` null-guard** (`shell/page.tsx:151-164`). `useExamTimer` is
   called with `?? 0` before the session loads. The hook's comment
   (`useExamTimer.ts:8-16`) explains a subtle bug: resync and expiry-check in two
   effects could see a stale `secondsLeft` and fire `onTimeUp` spuriously. Fixed by
   merging into one effect keyed on `initialSeconds`, plus `if (!examConfig) return`
   in the shell. **When you add Writing's time-up behaviour, preserve both guards.**

3. **The skill branching is already conditional**, and Reading already carves out
   exceptions: no generic submit button (`:222`), no padded scroll container
   (`:238-243`), its own force-submit signal (`:59`). Writing will need the same
   kind of carve-out. Follow the precedent rather than inventing a new mechanism.

### Step C — Rendering the tasks (what exists today)

`shell/page.tsx:254-301` is the current Writing UI. It is a **placeholder**: a
2-column grid, two textareas, prompts read as
`session.questions[0].questions[0].prompt` and `[1].prompt`. No word counter, no
stimulus, no tabs, no per-task submit. This is what GOA-058 replaces.

**The shape of `questions` is the trap.** Two shapes exist:

```
REAL DATA — data/parsed/IELTS14/writing/test1.json     TEST FIXTURE — test_e2e_exam.py:216
{                                                       {
  "questions": [                <- a LIST                 "questions": {          <- a DICT
    {"number":1, "prompt":"…", "question_type":"…"},        "task1": {"prompt":"…",
    {"number":2, "prompt":"…", …}                                     "image_s3_key":"…"},
  ]                                                         "task2": {"prompt":"…"}
}                                                         }
                                                        }
```

`_question_list` (`session_service.py:527-538`) normalises **either** into a list for
the *public* payload. But `_resolve_task_context` (`:640-645`), used on submit,
does `questions_data.get("task1")` — which **only works on the dict shape**. Against
real ingested data it calls `.get` on a list → `AttributeError` → 500.

See §5 and §8.7. This is a real backend bug you must know about even though it
isn't yours to fix.

### Step D — Task 1 submit

| Question | Answer |
|---|---|
| **Component** | Your new `WritingExam` |
| **Hook** | Local `useState` for drafts and per-task status |
| **API** | ⚠️ **Does not exist yet.** `submitSession` (`exam-api.ts:119`) sends `{answers}` only |
| **Endpoint** | `PUT /api/exam/sessions/:id/submit` |
| **Service** | Exam. `submit_session` (`:119`) → early-branches to `_submit_writing` (`:143-144`) |
| **Data back** | `{session_id, task_number, status, overall_band, word_count, penalty_flag}` |
| **Rendered by** | Your new `TaskResultCard` |
| **Stored** | Server: `exam_writing_responses` row. Client: local state |
| **Why** | Per-task submit exists *precisely* so Task 1 can be graded while Task 2 is still being written |

What `_submit_writing` does, in order (`session_service.py:550-629`):

```
1. validate task_number and essay_text present               → 400 if not
2. word_count   = len(essay_text.split())
   penalty_flag = (task 1 and wc < 150) or (task 2 and wc < 250)
3. save_response(...)    UPSERT — resubmitting a task overwrites and NULLs the
                         old evaluation (writing_response_repository.py:31-44)
4. _resolve_task_context(...)  → (task_prompt, stimulus_s3_key)
5. writing_client.evaluate_exam_essay(...)   → Writing service (502 on failure)
6. save_evaluation(...)  persist the full evaluation JSONB
7. if both task rows now exist: session.submit() + mark_scored()
8. return {status: "task_submitted" | "submitted", overall_band, word_count, penalty_flag}
```

Note step 8 carefully: **`evaluations` is not in the response.** The full
per-criterion data is computed at step 5 and persisted at step 6, then thrown away
on the way out. That's the gap discussed in §5.

Note the state machine in step 7 — the session only flips to `submitted`/`scored`
when **both** rows exist. The comment at `:545-548` explains why: it keeps
`GET /:id` and `GET /:id/result`'s existing `{"submitted","scored"}` status checks
working unchanged. Task 1 submit leaves the session `in_progress`, so the timer
keeps running and Task 2 remains submittable. Elegant — one state machine serves
both the per-task and whole-exam views.

### Step E — Task 2 submit and the combined result

Identical path, `task_number: 2`. On return, `status === "submitted"`, so navigate
to `/exam/results?session=…&skill=Writing`.

`GET /api/exam/sessions/:id/result` → `get_result` → branches to
`_get_writing_result` (`:647-683`):

```python
band_task1 = tasks[1].evaluation.overall_band
band_task2 = tasks[2].evaluation.overall_band
overall_band = round((band_task1 + 2 * band_task2) / 3 * 2) / 2   # nearest 0.5
return {session_id, user_id, skill_area, overall_band, tasks}
```

`(t1 + 2·t2)/3` **is** the 33/67 weighting — Task 2 counts double. Verify the
ticket's example:

```
(6.5 + 2×7.0)/3 = 20.5/3 = 6.8333…
6.8333 × 2 = 13.666… → round → 14 → /2 = 7.0      ✅ matches "6.8 → Band 7.0"
```

Good. The backend already produces exactly the number the AC demands. **Your job is
to display the formula, not to recompute the band.** If you compute it client-side
you introduce a second source of truth that will drift.

Also note `_get_writing_result` **404s when fewer than two responses exist**
(`:655-659`). So this endpoint cannot serve the Task 1 compact card.

## 2.4 Data model

```
exam_db.questions
  id · book_ref · test_number · exam_type · skill_area
  passage_text · audio_s3_key · questions (JSONB) · answer_key (JSONB)
                                    │
                                    └── writing: task prompts (+ image_s3_key, in theory)

exam_db.exam_sessions
  id · user_id · question_id · exam_type · skill_area
  status (in_progress|submitted|scored|abandoned)
  started_at · time_limit_seconds · last_heartbeat_at

exam_db.exam_writing_responses          ← created by GOA-053 (migration 004)
  id · session_id FK · task_number (1|2)
  response_text · word_count · penalty_flag · evaluation_result (JSONB)
  UNIQUE (session_id, task_number)      ← makes resubmission idempotent

writing_db.essays
  id · user_id · extracted_text · submission_type · exam_type
  exam_session_id · task_number · evaluation_cache_key · evaluation_result
```

Two databases hold overlapping data on purpose. `writing_db.essays` is the Writing
service's own record (for caching, cost tracking, observability);
`exam_db.exam_writing_responses` is the Exam service's record (the authoritative
exam artefact). Each service owns its own data — no cross-database joins. That's
standard microservice discipline: the price is duplication, the payoff is that
either service can evolve its schema without breaking the other.

---

# Step 3 — File-by-file walkthrough

Live code review. For each file: why it exists, what it owns, who calls it, who it
calls, whether you'll modify it, and blast radius.

---

### `services/frontend/app/exam/page.tsx` — exam prep landing

- **Why** Entry point. Academic/General toggle, four skill cards, session resume.
- **Owns** Exam-type selection and session creation.
- **Called by** Router (`/exam`).
- **Calls** `createSession()`, `PATCH /api/profile`, `router.push`.
- **Modify?** ❌ No.
- **Blast radius** Shared by all four skills. Leave it alone.
- **Review notes** `userId` hardcoded (line 52, TODO). `alert()` for errors (line 68)
  — crude but not yours. The `PATCH /api/profile` at line 38 has no `.catch()`;
  a rejected promise there is an unhandled rejection. Pre-existing; note it, don't
  fix it in this ticket.

---

### `services/frontend/app/exam/shell/page.tsx` — the exam shell ⭐

- **Why** The exam-taking chrome shared by every skill: header, timer, heartbeat,
  submit modal, skill dispatch.
- **Owns** Session loading, timer wiring, heartbeat, per-skill branching.
- **Called by** Router (`/exam/shell?session=…`).
- **Calls** `getSession`, `sendHeartbeat`, `submitSession`, `useExamTimer`,
  `<ReadingExam>`.
- **Modify?** ✅ **Yes** — replace lines 254-301 with your `<WritingExam>`, pass
  `secondsLeft` down, exclude Writing from the generic submit button, keep the
  full-screen `evaluating` overlay away from Task 1.
- **Blast radius** ⚠️ **High.** Reading and Speaking share this file. Guard every
  change behind `examConfig.skill === "Writing"`. Do not restructure the header,
  the timer wiring, the heartbeat effect, or Reading's container carve-out.
- **Review notes** `executeSubmission` (line 120) is hardcoded to Writing's *old*
  payload shape — that's the function you're superseding. `handleTimeUp` already
  special-cases Reading; you'll add a Writing case. Note `status === "evaluating"`
  triggers a full-screen overlay at line 318 — **this is exactly the blocking
  spinner the AC forbids for Task 1.** Keep Task 1's status local to `WritingExam`
  so it can never reach the shell's `status`.

---

### `services/frontend/app/exam/results/page.tsx` — results ⭐

- **Why** Post-exam results for every skill.
- **Owns** Result fetching, Reading's sessionStorage read, profile score sync.
- **Calls** `getResult`, `getSession`, `loadReadingResult`, `<ReadingResultsView>`.
- **Modify?** ✅ **Yes** — add a Writing branch.
- **Blast radius** ⚠️ Medium. Reading has an early-return branch (lines 51-77);
  everything else falls to the generic path. Add Writing as a **third branch**, don't
  rewrite the dispatch.
- **Review notes** Lines 187-208 render **hardcoded fake data** — `"Task 1 (Band 7.0)"`
  and invented feedback prose. That is a placeholder from the design-shot era and it
  must go. Worse, `getResult` is typed `ExamResultResponse` (`band_score`, `raw_score`)
  but writing returns `{overall_band, tasks}` — so `result.band_score` is `undefined`,
  the banner renders empty, and `update-scores` posts `bandScore: undefined`.
  TypeScript didn't catch it because the type is a *claim* about an untyped
  `response.json()`, not a verified fact. **Lesson: a hand-written API type is a
  promise, not a proof. Check it against the server.**

---

### `services/frontend/app/hooks/useExamTimer.ts`

- **Why** One countdown, seeded from the server, shared by all skills.
- **Owns** `secondsLeft`, `formattedTime` (mm:ss), `isCritical` (≤ 5 min).
- **Called by** The shell. **Calls** nothing.
- **Modify?** ❌ **No.** It already returns `secondsLeft`; derive elapsed as
  `time_limit_seconds - secondsLeft`.
- **Blast radius** ⚠️ **High** — every skill. Touch it and you can resurrect the
  spurious-`onTimeUp` bug documented in its own comment.
- **Review notes** `onTimeUpRef.current = onTimeUp` on every render (line 6) keeps
  the latest callback without re-running the interval effect — a deliberate,
  correct idiom. Don't "clean it up" into a dependency.

---

### `services/frontend/lib/exam-api.ts` ⭐

- **Why** Typed client for exam endpoints, through the Gateway.
- **Owns** `API_BASE`, exam-type/skill mapping (`"Academic"` → `"academic"`),
  request shapes, error throwing.
- **Called by** exam page, shell, results, reading components.
- **Calls** `fetch` → Gateway.
- **Modify?** ✅ **Yes** — add `submitWritingTask()` and `getWritingResult()` + types.
- **Blast radius** 🟢 **Low if additive.** ⚠️ High if you change `submitSession`,
  which Reading/Speaking paths touch. **Add new functions; don't repurpose old ones.**
- **Review notes** Every function repeats `if (!response.ok) throw new Error(await response.text())`.
  Fine — consistency over abstraction at this size. The `credentials: "include"` in
  `fetchOptions` is load-bearing: auth is HttpOnly cookies, and omitting it gets you
  a 401 that looks like a routing bug.

---

### `services/frontend/components/chat/essay-highlighter.tsx` ⭐ REUSE

- **Why** Renders essay text with coloured `<mark>` spans and Radix tooltips.
- **Owns** Overlap resolution, segment building, the criterion colour map.
- **Called by** `writing-evaluation-panel.tsx`. **Calls** `@radix-ui/react-tooltip`.
- **Modify?** ❌ **No — reuse as-is.**
- **Blast radius** ⚠️ Changing it affects the chat writing path (GOA-043) and its
  174-line unit test.
- **Review notes** Its `CRITERION_COLOURS` (lines 27-55) is **exactly** the palette
  GOA-058 asks for:

  | Criterion | Colour | AC requirement | Match |
  |---|---|---|---|
  | `grammar` | `rgba(255,77,77,…)` red | Grammar red | ✅ |
  | `vocabulary` | `rgba(59,130,246,…)` blue | Vocabulary blue | ✅ |
  | `cohesion` | `rgba(255,140,0,…)` orange | Cohesion orange | ✅ |
  | `task_response` | `rgba(139,92,246,…)` purple | Task Response purple | ✅

  **Do not redefine these colours.** If they must be shared more widely, export them
  — don't copy-paste a second palette that will drift.

  `resolveNonOverlappingIssues` (lines 77-102) drops invalid ranges and resolves
  overlaps first-match-wins. Defensive against LLM output. Its interface is
  `EssayIssue = HighlightedIssue & { criterion: string }` where `HighlightedIssue`
  is `{text, issue, suggestion, start, end}`.

  ⚠️ **The backend does not emit that shape.** See §5.7.

---

### `services/frontend/components/chat/writing-evaluation-panel.tsx` — reference

- **Why** Chat-mode evaluation panel: bars, overall band, highlighter, print CSS.
- **Modify?** ❌ No. It's chat-shaped (`Record<string, {band, feedback}>`, paid-tier
  "improved essay", `window.print()`), not exam-shaped.
- **Review notes** Read lines 38-64 anyway. `CRITERION_ALIASES` normalises the
  **two parallel naming schemes** in this codebase:

  ```
  evaluations map keys:      task_achievement · coherence · lexical · grammar
  CriterionEvaluation.criterion: task_response · cohesion · vocabulary · grammar
  ```

  That is a real, live inconsistency, and the alias map is how the existing code
  survives it. **Pick `task_response`/`cohesion`/`vocabulary`/`grammar` as canonical
  for GOA-058** — it's what the exam endpoint returns — and reuse the alias idea if
  you ever meet the other spelling.

---

### `services/frontend/components/reading/*` — your structural template

`ReadingExam.tsx` (272 lines) shows the pattern: one top-level feature component
owns state and submission, the shell just mounts it. `SectionTabs.tsx` (41 lines) is
your tab template — `role="tablist"`, `role="tab"`, `aria-selected`,
`data-testid="section-tab-N"`. Copy its structure and accessibility attributes.
`SubmitConfirmModal.tsx` exists as a separate component (rather than reusing the
shell's generic modal) because it needs unanswered-count logic — precedent for
Writing owning its own submit affordances.

- **Modify?** ❌ No. **Blast radius** Reading only.

---

### `services/exam/app/services/session_service.py` ⭐ backend brain

- **Why** All exam business logic.
- **Owns** Session lifecycle, timers, grading dispatch, writing sub-flow, weighting.
- **Called by** `api/sessions.py`, `api/reading.py`, `api/listening.py`.
- **Calls** repositories, `GradingService`, `TimerService`, `WritingClient`.
- **Modify?** ⚠️ **One line**, discussed in §5.9 and §6.
- **Blast radius** ⚠️ **High** — every skill runs through it. An **additive** key in a
  returned dict is about as safe as backend changes get, but it is still a backend
  change on a frontend ticket. Justify it explicitly in the PR.
- **Review notes** `_resolve_task_context` (lines 631-645) is the list-vs-dict bug
  (§2.3 Step C). And `_get_writing_result` carries this comment at line 674:

  > `# IELTS weighting: Task 2 counts twice Task 1. Confirm this is what you want.`

  Consider it confirmed — GOA-058's AC states 33/67 explicitly and the arithmetic
  reproduces the ticket's worked example exactly. Worth a PR comment removing the
  uncertainty.

---

### `services/exam/app/api/sessions.py`

- **Why** Thin FastAPI router.
- **Review notes** Line 49: `session["remaining_time_seconds"] = session.pop("remaining_seconds")`
  — the service says `remaining_seconds`, the wire says `remaining_time_seconds`, and
  the router renames it. Fragile (a plain dict, no response model) but working.
  Line 21: `dependencies=[Depends(validate_internal_api_key)]` — this is *why* the
  browser can't call the exam service directly, and why BUG-046 mattered.
  **Modify?** ❌ No.

---

### `services/writing/app/routers/essays.py` + `agents.py` + `evaluation.py`

- **Why** The LLM evaluation engine.
- **Modify?** ❌ **No.** "Reuse the existing Writing evaluation infrastructure" in the
  ticket means *exactly this*: don't build a second evaluation path.
- **Review notes** `evaluation.py:172-174`:

  ```python
  is_academic_task1 = exam_type.lower() == "academic" and task_number == 1
  if is_academic_task1 and not stimulus_s3_key:
      raise EvaluationFailed("Academic Task 1 requires a stimulus image.")
  ```

  **Academic Task 1 hard-fails without a stimulus key.** Combined with the fact that
  no ingested question *has* one (§5.2), the Academic writing exam cannot complete
  against a real backend today. Know this before you debug a 502 for an hour.

---

### `services/frontend/test/e2e/reading-exam.spec.ts` ⭐ copy this

- **Why** Full Reading flow E2E without a live backend.
- **Modify?** ❌ No — **copy its helpers into your new spec.**
- **Review notes** Lines 6-17 explain the three things people get wrong:
  1. Mock the **Gateway** origin (`localhost:8080/api/exam`), not the service port.
  2. Cross-origin + JSON + `credentials:"include"` ⇒ the browser sends a **CORS
     preflight `OPTIONS`** first. Handle it or every mock silently fails.
  3. `credentials:"include"` forbids a wildcard `Access-Control-Allow-Origin`; you
     need the explicit origin plus `Access-Control-Allow-Credentials: true`.

  `corsHeaders()`, `fulfillJson()`, `withPreflight()` are ~30 lines that will save
  you an afternoon. Copy them.

---

### `services/frontend/test/e2e/exam-flow.spec.ts` ⚠️ stale

- **Modify?** ✅ **Yes, necessarily.**
- **Review notes** Its "Writing exam: Task 1 submission keeps Task 2 active" test
  (lines 42-67) does `page.locator("textarea").nth(1)`. With tabs, only one textarea
  is mounted, so it will fail. It's also **unmocked** — `getSession` fails, the shell
  redirects to `/exam`, and there is no textarea at all. It is not currently proving
  anything. Update it as part of your ticket and say so in the PR.

---

# Step 4 — The three dependency tickets

## 4.1 GOA-054 — Exam prep UI: type selection, skill cards, exam shell

**Problem solved.** Before it there was no way into an exam. It built the entry
point and the shared chrome.

**Files** (evolved across `f43dbf2`, `8f6e0d9`, `f7e6043`, then refined by GOA-055):

```
app/exam/page.tsx              exam type toggle + 4 skill cards + session create
app/exam/shell/page.tsx        header, timer, heartbeat, submit modal, skill dispatch
app/exam/results/page.tsx      generic results scaffold
app/hooks/useExamTimer.ts      countdown
app/types/exam.ts              ExamType, SkillArea, ExamStatus (incl. WritingStatus)
lib/exam-api.ts                createSession/getSession/submitSession/getResult/heartbeat
docs/adr/0002-exam-auth-and-routing.md
```

**APIs** `POST/GET/PUT /api/exam/sessions*`.

**Reuse** The shell (mount your component in it), `useExamTimer`, `Sidebar`, the
sessionStorage resume convention, the `lib/exam-api.ts` client pattern.

**Note `app/types/exam.ts` already ships this:**

```ts
export type WritingStatus =
  | "task1_submitted" | "task1_evaluating" | "task1_done"
  | "task2_writing"   | "task2_submitted"  | "task2_evaluating"
  | "combined_results";
```

Someone designed the Writing state machine ahead of time and nothing consumes it
yet. **Check whether it actually fits your flow before adopting it** — it's a
sketch, not a contract. `task1_evaluating` and `task2_writing` are concurrent in the
real flow, which a single union type can't express. You likely need *two
independent per-task statuses* rather than one global one. Adopt what fits, ignore
what doesn't, and don't contort your design to honour a placeholder.

**Must understand before GOA-058:** the Suspense requirement, the heartbeat
contract, the `handleTimeUp` guard, and that the shell is shared by four skills.

## 4.2 GOA-053 — Writing exam mode: per-task feedback + weighted result

**Problem solved.** Writing couldn't be examined. IELTS Writing is two tasks with
different rubrics, different minimum lengths, and 33/67 weighting — the generic
answer-key submit couldn't express any of that. Critically, it made **Task 1
gradable while Task 2 is still being written.**

**Files** (`5abe67b`, `65a16c1`):

```
services/exam/app/migrations/004_writing_exam_modes.sql     exam_writing_responses table
services/exam/app/migrations/005_add_writing_penalty.sql    penalty_flag column
services/exam/app/repositories/writing_response_repository.py
services/exam/app/services/writing_client.py                exam → writing HTTP client
services/exam/app/services/session_service.py               _submit_writing, _get_writing_result
services/writing/app/routers/essays.py                      POST /essays/evaluate/exam
services/writing/app/schemas.py                             ExamTaskEvaluation{Request,Response}
services/writing/app/agents.py                              exam-aware prompts, chart context
services/writing/migrations/004_add_task_number_to_essay.sql
services/exam/app/core/metrics.py                           task1/task2 latency histograms
```

**Infrastructure now available to you — this is the backbone of your ticket:**

| Capability | Where | Status |
|---|---|---|
| Per-task submit | `_submit_writing` | ✅ |
| Server-side word count | `len(essay_text.split())` | ✅ |
| Penalty flag (<150 / <250) | `session_service.py:568-570` | ✅ |
| Idempotent resubmit | UPSERT on `(session_id, task_number)` | ✅ |
| Session stays open after Task 1 | `status: "task_submitted"` | ✅ |
| Evaluation persisted per task | `save_evaluation` | ✅ |
| Weighted combination | `round((t1+2·t2)/3·2)/2` | ✅ |
| Prometheus latency per task | `goa_writing_exam_task{1,2}_evaluation_ms` | ✅ |
| **Evaluations returned on submit** | — | ❌ **missing** |

**Reuse** All of it. **Do not rewrite** the submit flow, the weighting, or the
penalty logic. Your job is to *surface* what this ticket built.

**Must understand:** the request contract (`task_number` + `essay_text` at the top
level, not inside `answers`), the `task_submitted` vs `submitted` distinction, and
the `_get_writing_result` 404-until-both-tasks rule.

Note the migration comment in `004_writing_exam_modes.sql` — a Supabase-style RLS
policy using `auth.uid()` aborted the whole migration on plain Postgres, so **004
and 005 were both unapplied and `exam_writing_responses` never existed in any
environment.** That's fixed now, but it explains why this path may be less
battle-tested than its ticket status implies. Expect to be the first person to run
it end to end.

## 4.3 GOA-043 — Writing interface polish: colour-coded feedback and diff view

**Problem solved.** Evaluation output was band numbers and prose. Students couldn't
see *where* in their essay a problem was. This added inline highlighting.

**Files** (`8038e12`):

```
components/chat/essay-highlighter.tsx          NEW — 199 lines
components/chat/writing-evaluation-panel.tsx   heavily extended (+242)
components/chat/chat-shell.tsx                 wiring
lib/writing-stream.ts                          evaluations_full, improved_essay
test/unit/essay-highlighter.test.tsx           NEW — 174 lines
vitest.config.ts / vitest.setup.ts             NEW — vitest introduced here
package.json                                   @radix-ui/react-tooltip, framer-motion
```

**Reuse — this is where the ticket's colour requirements come from:**

1. `<EssayHighlighter essayText issues />` — mount it in your expandable card.
2. `CRITERION_COLOURS` — the exact four AC colours.
3. `EssayIssue` type — `HighlightedIssue & {criterion}`.
4. The `criterion → colour` mapping idea for bars/badges.
5. **The vitest setup itself.** GOA-043 introduced unit testing to this frontend;
   `test/unit/essay-highlighter.test.tsx` is your worked example.

**Do NOT rewrite** `essay-highlighter.tsx` (unit-tested, chat depends on it),
`writing-evaluation-panel.tsx` (chat-shaped), or the SSE stream path.

**Must understand:** `EssayHighlighter` needs `{start, end, issue, suggestion, criterion}`.
The exam backend returns `{start_char, end_char, issue_type, suggestion}`. **You need
an adapter.** See §5.7.

## 4.4 What each dependency gives you, at a glance

```
 GOA-054  ──▶  a shell to mount into, a timer, an API client, a results page
 GOA-053  ──▶  a per-task backend that grades Task 1 without blocking Task 2
 GOA-043  ──▶  a highlighter and the exact four criterion colours

 GOA-058  ──▶  the UI that finally lets a student USE all three.
```

Your ticket is 3 story points because it is **mostly assembly**. If you find
yourself writing an LLM call, a weighting formula, or a highlighter, stop — it
already exists.

---

# Step 5 — Every acceptance criterion analysed

Legend: 🎨 UI only · 🔌 needs API wiring · ⚙️ needs backend change · ⚠️ blocked/at risk

---

### 5.1 🎨 Two-panel layout: Task 1 and Task 2 as tabs

**Why** Real IELTS Writing shows one task at a time. Tabs also solve a layout
problem: a stimulus image + a 250-word textarea + a word counter + feedback does not
fit in half a screen.

**Files** new `components/writing/WritingTaskTabs.tsx`, `WritingExam.tsx`;
`app/exam/shell/page.tsx` (lines 254-301 replaced).
**Reuse** `components/reading/SectionTabs.tsx` — structure and a11y attributes.
**Backend** none. **Already implemented?** No — current UI is a 2-column grid.

⚠️ **Consequence:** only one textarea is mounted at a time. This breaks
`exam-flow.spec.ts`'s `textarea.nth(1)` assertion. Plan for it.

⚠️ **Tension with "Task 2 remains fully editable":** with tabs, Task 2 is not
*visible* during Task 1 evaluation. Interpret "editable" as *"not disabled, not
blocked — switch to the tab and keep typing."* Preserve Task 2's draft in state
across tab switches (don't unmount-and-lose, or use `hidden` rather than conditional
render). Flag the interpretation in your PR.

---

### 5.2 ⚠️⚙️ Academic Task 1: stimulus image above textarea with zoom button

**Why** Academic Task 1 *is* "describe this chart." Without the chart the task is
meaningless. Zoom exists because axis labels are unreadable at panel size.

**This is the ticket's biggest problem.** Four independent gaps:

1. **No API field.** `_public_question` (`session_service.py:476-490`) returns
   `id, book_ref, test_number, exam_type, skill_area, passage_text, audio_s3_key, questions`.
   No image field. `QuestionResponse` (a Pydantic model) would strip any top-level
   addition anyway.
2. **No pre-signing.** The only pre-signer is `S3AudioDeliveryService` for listening
   audio (`audio_delivery_service.py:59`). Nothing pre-signs images.
3. **No data.** Real parsed writing JSON is a list of `{number, prompt, …}` with no
   image key. The chart survives only as OCR noise inside `prompt`
   (`"Sodium Saturated fat\nB\nB0\nPRORXRRI"`). `image_s3_key` exists **only** in the
   exam service's unit-test fixture (`test_e2e_exam.py:217-220`), and
   `005_seed_writing_questions.sql` is a **zero-byte file**.
4. **No Next.js image config.** `next.config.ts` has no `images.remotePatterns`;
   Next 16 throws at runtime on an unconfigured remote `src`.

**Verdict.** Ingesting stimulus images, adding a pre-sign service, exposing the URL,
and re-seeding is a multi-point **backend** ticket. GOA-058 is `Service: Frontend`.

**Recommendation:** build the frontend against a defined nullable contract —
`questions[0].questions[0].stimulus_image_url` — render image + zoom when present,
degrade to prompt-text-only when absent (which is what real data gives today, so
nothing crashes). Drive the E2E from route mocks, which is already this repo's
pattern. Use `unoptimized` on the `<Image>`: pre-signed URLs carry expiring query
strings, so routing them through Next's optimizer cache is *wrong*, not merely
convenient. **File the backend gap as its own ticket.**

**Files** new `components/writing/StimulusPanel.tsx`.
**Already implemented?** No, and not implementable end-to-end this ticket.

---

### 5.3 🎨 General Training Task 1: letter scenario text above textarea

**Why** GT Task 1 is a letter, not a chart. Its scenario is prose.

**Files** `StimulusPanel.tsx` branches on `examConfig.type`.
**Backend** Already there — `exam_type` is on the session and the shell already maps
it (`shell/page.tsx:74`). The parser already detects letters
(`writing_parser.py:104-105`).
**Good news:** this half of the AC is fully achievable today. GT needs no image.

---

### 5.4 🎨 Word counter — live, orange below target, green at target

**Why** IELTS penalises under-length responses. Students need live feedback.

**Implementation note from the ticket:**
```ts
string.trim().split(/\s+/).filter(Boolean).length
```
Trace the edge cases yourself:
- `""` → `trim()` → `""` → `split(/\s+/)` → `[""]` → `filter(Boolean)` → `[]` → **0** ✅
- `"a   b"` → `["a","b"]` → **2** ✅
- `"a\n\nb"` → `["a","b"]` → **2** ✅
- `"hello , world"` → `["hello", ",", "world"]` → **3** ⚠️

That last one is why the DoD says "punctuation-only tokens": a standalone `,`
**counts as a word** under this algorithm. Your unit test must **pin the specified
behaviour**, not the behaviour you think is more correct. If you "fix" it you diverge
from the server's `len(essay_text.split())`, which is the same algorithm — and a
counter that disagrees with the penalty flag is worse than a counter that counts a
comma.

**Ambiguity to resolve:** the AC says *"Orange below target (140/240), Green at
target (150/250)"* while the tests say 148 → orange, 150 → green. The consistent
reading is a **single boundary at the target**: orange while `count < target`, green
at `count >= target`; 140/240 are illustrative below-target values. State this
assumption in the PR.

**Files** `lib/writing-exam.ts` (the pure function — it must be unit-testable
without a DOM), `components/writing/WordCounter.tsx`.
**Backend** none. **Already implemented?** No.

---

### 5.5 🎨 Recommended time indicator — "Suggested: 20 min for Task 1"

**Why** 60 minutes for both tasks; the standard split is 20/40 (matching the 33/67
weighting — you spend twice the time on the task worth twice as much). Real IELTS
prints this on the paper; the parsed prompts even contain
*"You should spend about 20 minutes on this task."*

**Files** `WritingExam.tsx`.
**Reuse** `useExamTimer`'s `secondsLeft`; elapsed = `time_limit_seconds - secondsLeft`.
**Backend** none — `time_limit_seconds` already arrives.
**Modify the hook?** ❌ No.

---

### 5.6 🎨 Plain textarea (no rich text)

**Why** Real IELTS gives no formatting. Bold/italic would also corrupt the character
offsets the highlighter depends on (§1.6). And the AC is *already satisfied* by the
current placeholder.

**This is a "do not do" AC.** Do not add a rich-text editor. Keep `<textarea>`.

---

### 5.7 🔌 Inline colour-coded feedback (grammar red / vocab blue / cohesion orange / task response purple)

**Why** GOA-043 established this vocabulary; the exam view must match so students
learn one colour language.

**Reuse** `EssayHighlighter` + `CRITERION_COLOURS` — an exact colour match (§3).

⚠️ **Field-name mismatch — this AC silently fails without an adapter:**

```
Frontend expects (lib/writing-api.ts:12-26, via GOA-043):
    CriterionEvaluation { criterion, band_score, feedback, highlighted_issues[] }
    HighlightedIssue    { text, issue,      suggestion, start,      end }

Backend actually returns (writing/app/schemas.py:36-57):
    CriterionEvaluation { criterion, band_score, feedback, improvement_tip,
                          word_count, inline_issues[] }
    InlineIssue         { text, issue_type, suggestion, start_char, end_char }
```

Three renames (`issue`→`issue_type`, `start`→`start_char`, `end`→`end_char`) plus a
container rename (`highlighted_issues`→`inline_issues`). Feed the raw payload to
`EssayHighlighter` and you render **zero highlights, with no error** — the worst
kind of failure.

**Fix:** a ~10-line `toEssayIssues()` mapper in `lib/writing-exam.ts`.
**Do not** "fix" `writing-api.ts` or `EssayHighlighter` — the chat path (GOA-043)
depends on the current shape and is unit-tested against it. Adapt at the boundary.

---

### 5.8 🎨 Results: Task 1 and Task 2 side by side, explicit 33/67 weighting

**Why** Students must see *why* their overall band is what it is, and that Task 2
dominates.

**Files** new `components/writing/CombinedWritingResults.tsx`;
`app/exam/results/page.tsx` gets a Writing branch.
**Backend** ✅ **fully supported.** `_get_writing_result` returns
`{overall_band, tasks:{1:{response_text, word_count, penalty_flag, evaluation}, 2:{…}}}`.
**Already implemented?** ❌ — currently **hardcoded fake data** (`results/page.tsx:187-208`). Delete it.

---

### 5.9 ⚙️ After Task 1 submit: compact card with band + **top issue per criterion**, expandable, collapsed by default

**Why** Feedback while Task 2 is still open, without stealing screen space or
attention. Collapsed-by-default is deliberate: a student mid-exam should not be
pulled into a detailed post-mortem.

⚠️ **"Top issue per criterion" is not currently reachable by the browser.**

```
_submit_writing returns (session_service.py:622-629):
    { session_id, task_number, status, overall_band, word_count, penalty_flag }
                                          ▲
                          the ONLY score-ish thing you get

but two lines earlier (:607-611) the FULL evaluation was persisted:
    save_evaluation(session_id, task_number, evaluation.model_dump())
```

The data is computed, persisted, and then discarded on the way out. And
`GET /result` **404s until both tasks exist** (`:655-659`), so it can't fill the gap.

**Options:**

| Option | Verdict |
|---|---|
| Add `"evaluations"` to the submit response | ✅ **Recommended.** One additive line. |
| New `GET /sessions/:id/writing/:task` endpoint | ❌ New route, gateway change, more surface |
| Relax `_get_writing_result` to allow 1 task | ❌ Changes semantics of "result"; riskier |
| Show only `overall_band`, drop per-criterion | ❌ Fails the AC |

The one-liner:
```python
"evaluations": [e.model_dump() for e in evaluation.evaluations],
```
plus an assertion in the existing `test_exm09_writing_submit_task1_only`.

Yes, that is backend work on a frontend ticket. It is one additive field on an
endpoint GOA-053 already built, and **there is no frontend-only alternative.**
Say so explicitly in the PR — a reviewer should never have to discover a
cross-service change on their own.

**"Top issue"** = the first `inline_issue` for that criterion, falling back to
`feedback` when a criterion produced none.

---

### 5.10 🎨 Task 2 fully editable while Task 1 evaluates + no blocking spinner

**Why** The heart of the ticket. Four LLM calls take ~10-30s. Blocking would steal
exam time. This is *why* GOA-053 built per-task submit.

⚠️ **Trap:** `shell/page.tsx:318` renders a full-screen `"Analyzing performance..."`
overlay whenever `status === "evaluating"`, and `executeSubmission` (`:124`) sets
exactly that. **Keep Task 1's status local to `WritingExam`.** It must never reach
the shell's `status`.

**Design:** per-task status (`idle | submitting | evaluated | error`), independent
per task. Task 1 submitting must not disable Task 2's textarea or its tab.

**Already implemented?** Partially — the *backend* supports it. The frontend has no
per-task submit at all.

---

### 5.11 🎨 Combined results page: large band + explicit formula

**Why** Transparency. `(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0`
teaches the student that Task 2 is worth double.

**Backend** ✅ Already computes exactly this (verified in §2.3 Step E).
**Critical instruction:** render the string, display the server's `overall_band`.
**Do not recompute client-side.** Two implementations of one rule always drift, and
when they do, the student sees arithmetic that doesn't add up.

---

### 5.12 🎨 Under-minimum word count warning, per task, exact wording

> "Responses under 150 words are penalised for Task Achievement (criterion 1)."

**Why** IELTS penalises under-length. The wording must be exact — it's a
user-facing claim about marking.

**Backend** ✅ `penalty_flag` already computed and persisted (`:568-570`, migration 005).
**But** you also need it *live, while typing*, before any submit — so compute it
client-side from the word counter *and* honour the server's `penalty_flag` in results.

**Ambiguity:** the string says 150 but the AC says "display per task", and Task 2's
minimum is 250. The consistent reading: show this exact string on whichever task is
under **its own** minimum. Store it as a frozen constant so a stray edit can't drift
it, and state the assumption in the PR.

---

### 5.13 Testing requirements

**Unit (vitest, `*.test.ts`):** word counter — multiple spaces, newlines,
punctuation-only tokens. This is only cheap if the counter is a **pure function in
`lib/`**. Let the test shape the design.

**E2E (playwright, `test/e2e/*.spec.ts`):** Academic image + zoom, 148→orange /
150→green, both tasks evaluated, weighted band displayed. All achievable with route
mocks (copy `reading-exam.spec.ts`'s CORS helpers). The image test is *only*
achievable with mocks, given §5.2.

---

### 5.14 Summary table

| # | AC | Type | Backend? | Exists? | Risk |
|---|---|---|---|---|---|
| 1 | Tabs | 🎨 | no | ❌ | low |
| 2 | Academic stimulus + zoom | ⚠️⚙️ | **yes, missing** | ❌ | **high** |
| 3 | GT scenario text | 🎨 | ✅ | ❌ | low |
| 4 | Word counter | 🎨 | no | ❌ | low |
| 5 | Time indicator | 🎨 | ✅ | ❌ | low |
| 6 | Plain textarea | 🎨 | no | ✅ | none |
| 7 | Inline colours | 🔌 | ✅ (adapter) | partial | medium |
| 8 | Side-by-side + 33/67 | 🎨 | ✅ | ❌ (fake) | low |
| 9 | Task 1 compact card | ⚙️ | **one line** | ❌ | medium |
| 10 | Task 2 editable / no spinner | 🎨 | ✅ | ❌ | medium |
| 11 | Combined formula | 🎨 | ✅ | ❌ | low |
| 12 | Under-minimum warning | 🎨 | ✅ | ❌ | low |

---

# Step 6 — Review of the proposed implementation plan

The plan under review is the one produced earlier in this session. I'm reviewing it
as a design document, not defending it.

## 6.1 Verdict

**Broadly sound; two real criticisms, one nit.** The backend gaps it identifies are
genuine and I re-verified each. Its main weakness is **component-count inflation**
for a 3-point ticket.

## 6.2 Step-by-step

### Step 1 — Backend: return `evaluations` from `_submit_writing`

- **Why** AC 5.9 is otherwise unreachable.
- **Necessary?** ✅ Yes. I checked all four alternatives (§5.9); this is the smallest.
- **Easier?** No.
- **Complexity?** Minimal — additive key, no existing consumer breaks.
- **Scope?** ⚠️ Technically outside "Service: Frontend." Justified, but **must be
  called out explicitly in the PR description**, not buried in the diff.
- **Risks** Low. `_submit_writing` is writing-only. Response is an untyped `dict`,
  so no schema to update.
- **Better?** No. **Verdict: keep.**

### Step 2 — `lib/writing-exam.ts` pure-logic module

- **Why** Unit-testability (DoD) and one home for the shared rules.
- **Necessary?** ✅ Yes — matches the `reading-grading.ts` / `reading-results.ts`
  precedent exactly.
- **Complexity?** None; it *reduces* it.
- **Risks** Scope creep — don't let it become a junk drawer. Word counter, targets,
  warning constant, issue adapter, top-issue picker, formula formatter. Nothing else.
- **Verdict: keep. This is the strongest step.**

### Step 3 — Extend `lib/exam-api.ts`

- **Why** The existing `submitSession` cannot express `task_number`/`essay_text`.
- **Necessary?** ✅ Yes.
- **Easier?** You *could* overload `submitSession` with optional params. **Don't** —
  Reading and Speaking call it, and widening a shared function's contract for one
  caller is how shared modules rot. Additive is correct.
- **Risks** Low if strictly additive.
- **Verdict: keep.**

### Step 4 — Six new components ⚠️ **my main criticism**

Proposed: `WritingTaskTabs`, `WordCounter`, `StimulusPanel`, `TaskResultCard`,
`WritingExam`, `CombinedWritingResults`.

- **Why** Separation of concerns.
- **Necessary?** ⚠️ **Not all of them.** Six components for 3 story points is
  inflated. Specifically:
  - `WordCounter` — likely ~20 lines of JSX with two props. Rendered in exactly one
    place. **Strong candidate for inlining** into the task panel. Extracting a
    component "in case we reuse it" is speculative generality; the *logic* is
    already shared via `lib/writing-exam.ts`, which is where reuse actually matters.
  - `WritingTaskTabs` — `SectionTabs` is 41 lines for the same job, so this is
    proportionate. Keep, but keep it that small.
  - The other four earn their place: `StimulusPanel` (Academic/GT branch + zoom
    modal), `TaskResultCard` (collapse state), `WritingExam` (orchestration),
    `CombinedWritingResults` (different page entirely).
- **Better alternative:** start with **four** components — `WritingExam`,
  `StimulusPanel`, `TaskResultCard`, `CombinedWritingResults` — plus tabs and word
  counter inline. Extract later *if* a file passes ~150 lines. Extraction is cheap
  after the fact; premature extraction costs indirection now and forever.
- **Missing from the plan:** an explicit decision on **how Task 2's draft survives a
  tab switch**. Conditional rendering unmounts the textarea. Either lift both drafts
  into `WritingExam` state (fine — they're strings) or use `hidden` styling. The plan
  implies the former but never says it, and this is precisely where AC 5.10 gets
  broken by accident. **Make it explicit before coding.**

### Step 5 — Shell integration

- **Why** The shell must mount the new component and stop applying generic behaviour.
- **Necessary?** ✅ Yes.
- **Risks** ⚠️ **Highest-risk step in the plan.** Shared by four skills.
- **Better?** Follow Reading's precedent exactly: branch on `examConfig.skill`,
  add nothing global. And **verify Reading and Speaking still work** after touching
  this file — don't just test Writing.
- **Verdict: keep, with elevated care.**

### Step 6 — Results page Writing branch

- **Why** AC 5.8 / 5.11; the current content is fabricated.
- **Necessary?** ✅ Yes.
- **Nit** The plan says "post `overall_band` to `update-scores`." That route
  **doesn't exist** — `app/api/` contains only `chat/`. So `/api/profile/update-scores`
  404s today. The Reading path already swallows this with a comment. Match the
  existing behaviour (fire-and-forget with `.catch()`); **don't build the missing
  route** — out of scope.
- **Verdict: keep, with that correction.**

### Step 7 — `next.config.ts` / image config

- **Why** `<Image>` on an unconfigured remote host throws.
- **Necessary?** ✅ Yes, in some form.
- **Assessment** The plan prefers `unoptimized` over `remotePatterns` and I agree —
  but its stated reason ("we don't know the S3 host yet") is the weaker one. The
  **real** reason is that pre-signed URLs carry expiring query strings and per-URL
  credentials; caching them in Next's image optimizer is semantically wrong. Right
  call, better justification.
- **Verdict: keep, `unoptimized`.**

### Step 8 — Tests

- **Why** DoD.
- **Necessary?** ✅ Yes, including the `exam-flow.spec.ts` update (which the plan
  correctly catches — the tabs change makes `textarea.nth(1)` impossible).
- **Missing:** the plan doesn't say to **run the existing suites** (`reading-exam.spec.ts`,
  `essay-highlighter.test.tsx`, the exam service's pytest) after the shell and
  `session_service.py` changes. Regression checks on shared files aren't optional.
- **Verdict: keep, plus explicit regression runs.**

## 6.3 What the plan gets right

- ✅ Correctly refuses to build the stimulus pipeline. That's the single most
  important scoping call in the ticket.
- ✅ Correctly declines the `sessionStorage` carry-forward pattern. Reading needs it
  because per-question results *only* exist in the submit response; Writing's
  `GET /result` returns everything. Copying a pattern without its justification is a
  classic cargo-cult error, and the plan avoided it.
- ✅ Correctly refuses to touch `EssayHighlighter` / `writing-api.ts`, adapting at
  the boundary instead.
- ✅ Correctly identifies that the backend already produces the exact band the AC
  example demands, and that the frontend should not recompute it.

## 6.4 What I'd change

1. **Four components, not six.** Inline the word counter and keep tabs tiny.
2. **Make the draft-persistence decision explicit** before coding (§6.2 Step 4).
3. **Add explicit regression runs** for Reading E2E, the highlighter unit test, and
   exam-service pytest.
4. **Flag the Gateway's 10s exam timeout as a known risk** (§1.4). Four LLM calls
   may exceed it. Not yours to fix, but you *will* hit it in manual testing and you
   should recognise it instantly rather than debugging your own code.
5. **Correct the `update-scores` assumption** (§6.2 Step 6).

## 6.5 Scope discipline — the "do not build" list

- ❌ Stimulus image ingestion / S3 upload / pre-sign service
- ❌ Fixing `_resolve_task_context`'s list-vs-dict bug (file it)
- ❌ Seeding writing questions
- ❌ The `/api/profile/update-scores` route
- ❌ Changes to `EssayHighlighter`, `WritingEvaluationPanel`, `writing-api.ts`, the chat path
- ❌ Rich text editing
- ❌ Changes to the writing service's evaluation logic
- ❌ Refactoring `useExamTimer` or the shell's header/heartbeat

---

# Step 7 — The mental model

## 7.1 The examination-centre analogy

```
  ┌─────────────────────────────────────────────────────────────────┐
  │  FRONTEND  =  the examination room + the answer booklet          │
  │     Where the candidate sits. Shows the clock, the question       │
  │     paper, the paper they write on. Enforces nothing — it is      │
  │     furniture and stationery. Pleasant, but not authoritative.    │
  ├─────────────────────────────────────────────────────────────────┤
  │  GATEWAY  =  the invigilator at the door                          │
  │     Checks your ID (JWT). Stops you bringing things in (CORS,     │
  │     rate limit). Carries papers to the back office and never      │
  │     lets you walk back there yourself. Holds the keys you are     │
  │     never given (INTERNAL_API_KEY).                               │
  ├─────────────────────────────────────────────────────────────────┤
  │  EXAM SERVICE  =  the exam board / registrar                      │
  │     Decides which paper you get. Starts the official clock.       │
  │     Records what you handed in and when. Marks the objective      │
  │     papers itself. Sends the subjective ones to an examiner.      │
  │     Combines marks into a final grade. THE AUTHORITY ON TIME      │
  │     AND ON WHAT WAS SUBMITTED.                                    │
  ├─────────────────────────────────────────────────────────────────┤
  │  WRITING SERVICE  =  the panel of four specialist examiners       │
  │     Four examiners read the same essay independently — one for    │
  │     task response, one for cohesion, one for vocabulary, one      │
  │     for grammar — so no one's impression contaminates another's.  │
  │     They confer only to average. If one cannot mark, the whole    │
  │     paper is returned unmarked rather than averaged over three.   │
  ├─────────────────────────────────────────────────────────────────┤
  │  SESSION  =  the answer booklet with your candidate number        │
  │     Issued when you sit down, stamped with a start time, has a    │
  │     state (being written / handed in / marked / abandoned).       │
  │     THE HEARTBEAT IS YOU RAISING YOUR HAND TO SHOW YOU'RE STILL   │
  │     THERE — stop, and the invigilator collects your paper.        │
  ├─────────────────────────────────────────────────────────────────┤
  │  EVALUATION  =  the marked-up script                              │
  │     Four criterion scores, prose feedback, and pencil marks in    │
  │     the margin pointing at exact phrases (the character offsets). │
  ├─────────────────────────────────────────────────────────────────┤
  │  RESULT  =  the certificate                                       │
  │     One number, computed from the parts by a published rule,      │
  │     issued only when the whole paper is complete.                 │
  └─────────────────────────────────────────────────────────────────┘
```

## 7.2 Six design decisions and their reasons

**1. Why doesn't the browser call the Writing service directly?**
It would let a client fabricate an evaluation for a session it doesn't own, skip
persistence, skip the penalty flag, and skip the word count. The Exam service must
record the response *before* grading — that ordering is what makes the exam
auditable. Also, the browser can't be trusted with `INTERNAL_API_KEY` (BUG-046).

**2. Why per-task submit instead of one submit at the end?**
Because IELTS Writing is genuinely two independent tasks with different rubrics and
different weights — and because the candidate is still working. Grading Task 1
immediately turns dead time (four parallel LLM calls) into useful feedback without
taking a second of exam time. **The whole "no blocking spinner" AC is downstream of
this one architectural choice.**

**3. Why does the session stay `in_progress` after Task 1?**
Because it *is*. The candidate is still writing. Flipping to `submitted` would stop
the timer, break `GET /result`'s status checks, and make Task 2 unsubmittable. The
`task_submitted` return value tells the client "your task landed" without lying
about the session.

**4. Why four LLM agents instead of one?**
Independence. One call scoring all four criteria anchors — a weak grammar
impression drags the vocabulary score down. Four criterion-specific prompts stay
independent and run concurrently, so latency is max(4), not sum(4). And a partial
failure fails loudly rather than quietly averaging three-quarters of an assessment.

**5. Why does the server compute character offsets by substring search?**
Because models are unreliable at arithmetic and reliable at quoting. Asking for
offsets directly yields plausible-looking wrong numbers; asking for exact quotes and
computing offsets with `str.find` yields either a correct offset or a dropped issue.
**Never ask a model for something you can compute deterministically.**

**6. Why does the server own the weighting?**
It's a marking rule, and marking rules belong with the marker. If the client
computed it, two implementations would drift and a student would eventually see
arithmetic that doesn't add up. The client's job is to *explain* the number, not
produce it.

## 7.3 The one-paragraph version

> The **frontend** is a thin, untrusted view over a stateful server-side exam. The
> **Gateway** is the only door, and it holds the keys. The **Exam service** owns
> time, state, and what was submitted; it never marks essays itself. The **Writing
> service** owns judgement and nothing else — it doesn't know what a session is.
> **Per-task submit** exists so that judgement can happen while the candidate keeps
> working, and every "no blocking spinner / Task 2 stays editable" requirement in
> GOA-058 is a direct consequence of that. Your ticket adds **no new capability** —
> it makes existing backend capability visible.

---

# Step 8 — Before you write code

### 8.1 Where would I tell a junior to start?

**Manually trace one request end to end before writing anything.** Start the stack,
open DevTools, click "Take Exam" on Writing, and watch the network tab. Then open
`session_service.py` and find the code that produced each response you just saw.

You will learn more in that 30 minutes than from any document — including this one.
Concretely: `POST /api/exam/sessions` → find `create_session`. `GET /api/exam/sessions/:id`
→ find `get_session` and the `remaining_seconds` rename. Then look at
`questions[0].questions` in the response and **see for yourself** whether it's a
list or a dict. That one observation is the ticket's biggest trap.

### 8.2 Which files first? (in order)

1. [`app/exam/shell/page.tsx`](../services/frontend/app/exam/shell/page.tsx) — where you'll work
2. [`lib/exam-api.ts`](../services/frontend/lib/exam-api.ts) — the API contract
3. [`session_service.py:550-683`](../services/exam/app/services/session_service.py#L550) — `_submit_writing` + `_get_writing_result`
4. [`components/reading/ReadingExam.tsx`](../services/frontend/components/reading/ReadingExam.tsx) — your structural template
5. [`components/reading/SectionTabs.tsx`](../services/frontend/components/reading/SectionTabs.tsx) — your tab template
6. [`components/chat/essay-highlighter.tsx`](../services/frontend/components/chat/essay-highlighter.tsx) — what you reuse
7. [`test/e2e/reading-exam.spec.ts`](../services/frontend/test/e2e/reading-exam.spec.ts) — testing pattern
8. [`writing/app/schemas.py:36-115`](../services/writing/app/schemas.py#L36) — the real evaluation shape
9. [`app/exam/results/page.tsx`](../services/frontend/app/exam/results/page.tsx) — the fake data you'll delete
10. [`app/hooks/useExamTimer.ts`](../services/frontend/app/hooks/useExamTimer.ts) — small, read the comment

### 8.3 Which files to ignore

`services/{speaking,rag,user,notification,ingestion}/`, `services/orchestration/`
(chat only — including the `.env.example` currently open in your editor),
`apps/web/`, `components/{landing,onboarding,auth,speaking}/`,
`app/{chat,speaking,profile,login,register}/`, `lib/{speaking-*,audio-*,chat-stream,reading-*}.ts`,
`evals/`, `monitoring/`, `infra/`, `.next/`, `design-shots/`, `lighthouse-reports/`.

Two you'd *expect* to need but don't: `lib/writing-api.ts` and `lib/writing-stream.ts`
are the **chat** writing path. Read them once for context, then leave them alone.

### 8.4 APIs to understand first

```
1. PUT  /api/exam/sessions/:id/submit    {answers:{}, task_number, essay_text}
                                         ← the one that doesn't exist client-side yet
2. GET  /api/exam/sessions/:id/result    → {overall_band, tasks:{1:{…},2:{…}}}
3. GET  /api/exam/sessions/:id           → session + questions + remaining_time_seconds
4. POST /api/exam/sessions               → session_id  (already wired)
```

Plus, for context only (never called from the browser):
`POST /essays/evaluate/exam` on the Writing service.

### 8.5 Most important React components

**To read:** `ExamShellContent`, `ReadingExam`, `EssayHighlighter`, `SectionTabs`.
**To write:** `WritingExam` (the orchestrator — ~60% of your work),
`TaskResultCard`, `StimulusPanel`, `CombinedWritingResults`.

### 8.6 Backend endpoints that matter

| Endpoint | Handler | Status |
|---|---|---|
| `POST /sessions` | `create_session` | ✅ works |
| `GET /sessions/:id` | `get_session` | ✅ works, **but no stimulus URL** |
| `PUT /sessions/:id/submit` | `_submit_writing` | ✅ works, **but omits `evaluations`** |
| `GET /sessions/:id/result` | `_get_writing_result` | ✅ works, **404s until both tasks** |
| `PATCH /sessions/:id/heartbeat` | `heartbeat` | ✅ works |

### 8.7 Bugs you should already know about

| # | Bug | Impact | Yours? |
|---|---|---|---|
| 1 | `_resolve_task_context` does `.get("task1")` on a **list** → `AttributeError` → 500 (`session_service.py:640-645`) | Writing submit **500s on real data** | ❌ File it |
| 2 | Writing service **hard-fails** Academic Task 1 without a stimulus key (`evaluation.py:172-174`) | Academic writing can't complete | ❌ Same root cause as #1 |
| 3 | No stimulus image anywhere (§5.2) | AC 5.2 not achievable e2e | ❌ Separate ticket |
| 4 | `evaluations` missing from submit response | AC 5.9 unreachable | ✅ One line |
| 5 | Inline-issue field-name mismatch (§5.7) | Highlights silently render **empty** | ✅ Adapter |
| 6 | `results/page.tsx:187-208` renders **fake hardcoded data** | Wrong info shown to users | ✅ Delete |
| 7 | `getResult` mistyped for Writing → `band_score` undefined | Empty banner, `bandScore: undefined` posted | ✅ Fix in branch |
| 8 | `/api/profile/update-scores` **doesn't exist** → 404 | Scores never sync | ❌ Pre-existing |
| 9 | Gateway uses the **10s** client for exam routes (`server.go:48`) | 4 LLM calls may 502 at ~10s | ❌ Know it, don't fix it |
| 10 | `exam-flow.spec.ts` Writing test is unmocked and asserts `textarea.nth(1)` | Will fail with tabs | ✅ Update |
| 11 | `userId` hardcoded (`exam/page.tsx:52`) | All sessions same user | ❌ Pre-existing |
| 12 | Migrations 004/005 were long unapplied (RLS abort) | Writing exam path is lightly exercised | ❌ Expect to be first |

Bug #9 deserves emphasis: when your first real Task 1 submit returns 502 after
exactly ten seconds, it is **not your code**. It's the Gateway timing out while the
services are still working — "a gateway timeout wearing an upstream failure's
costume," in the words of whoever debugged it last.

### 8.8 Risky to modify

| File | Risk | Why |
|---|---|---|
| `app/exam/shell/page.tsx` | 🔴 High | Four skills share it |
| `app/hooks/useExamTimer.ts` | 🔴 High | All skills; subtle documented bug history |
| `session_service.py` | 🔴 High | All skills; **additive only** |
| `lib/exam-api.ts` existing fns | 🟠 Medium | Reading/Speaking callers — **add, don't change** |
| `app/exam/results/page.tsx` | 🟠 Medium | Reading branch — add a third branch |
| `components/chat/essay-highlighter.tsx` | 🟠 Medium | Chat depends on it; unit-tested |
| `next.config.ts` | 🟠 Medium | Global build config |

### 8.9 Completely safe

- Anything **new** under `components/writing/`
- A **new** `lib/writing-exam.ts`
- A **new** `test/unit/writing-exam.test.ts`
- A **new** `test/e2e/writing-exam.spec.ts`
- Deleting the fake results block (`results/page.tsx:187-208`) — nothing reads it
- Adding **new** exported functions to `lib/exam-api.ts`

### 8.10 The order I would implement in

```
 0. TRACE      Run the stack. Click through. Watch DevTools. Read the responses.
               Confirm for yourself: is `questions` a list or a dict?           [30 min]

 1. RESOLVE    Confirm the three assumptions with your tech lead:
               (a) word counter green at count >= target
               (b) tabs mean one textarea mounted; drafts lifted to WritingExam
               (c) the warning string is verbatim on both tasks
               Blocked-ish: (b) shapes the component tree. Ask early.

 2. PURE       lib/writing-exam.ts + test/unit/writing-exam.test.ts.
               Start here — no UI, no network, fastest feedback loop, and it
               satisfies a DoD item on day one.

 3. API        lib/exam-api.ts: submitWritingTask + getWritingResult + types.
               Verify by hand against the running backend (or curl) BEFORE
               building UI on top of an assumed shape.                    ← lesson of bug #7

 4. BACKEND    The one-line `evaluations` addition + its pytest assertion.
               Do it now so step 6 has real data to render.

 5. SKELETON   WritingExam with tabs + two textareas + word counters, mounted
               in the shell. No submit yet. Get the layout and the
               draft-persistence-across-tabs behaviour right first.

 6. SUBMIT     Per-task submit + TaskResultCard (collapsed, expandable).
               VERIFY EXPLICITLY: Task 2 stays editable, no full-screen overlay.

 7. STIMULUS   StimulusPanel: Academic image + zoom, GT scenario text,
               graceful fallback when no URL. `unoptimized`.

 8. RESULTS    CombinedWritingResults + the results-page Writing branch.
               Delete the fake data. Render the formula; display the
               SERVER's band.

 9. E2E        New writing-exam.spec.ts (copy reading-exam.spec.ts's CORS
               helpers). Update the stale exam-flow.spec.ts Writing test.

10. REGRESS    Run everything: vitest, reading-exam.spec.ts, exam-service
               pytest. Manually click through Reading and Speaking — you
               touched their shell.

11. PR         Call out explicitly: the backend one-liner and why; the three
               assumptions; the stimulus gap and the follow-up ticket for
               bugs #1/#2/#3.
```

Note steps 2-4 come before any component. That ordering is deliberate: **push work
down to where feedback is fastest and verification is cheapest.** A pure function
proves itself in milliseconds; a React component needs a browser; an integration
needs the whole stack. Every hour you spend at the bottom of that pyramid saves
three at the top.

---

## Appendix — The component tree you're building

```
app/exam/shell/page.tsx  (ExamShellContent)                       [MODIFY]
│
├── <Sidebar/>                                                    [reuse]
├── <header> skill · type badge · useExamTimer · submit           [reuse, carve out Writing]
└── <main>
    ├── skill==="Reading"  → <ReadingExam/>                       [untouched]
    └── skill==="Writing"  → <WritingExam/>                       [NEW] ⭐
        │     props: sessionId, session, examType, secondsLeft, timeLimitSeconds
        │     state: activeTask, drafts{1,2}, taskStatus{1,2}, evaluations{1,2}
        │
        ├── tabs (inline or <WritingTaskTabs/>)                   [pattern: SectionTabs]
        │
        ├── activeTask===1
        │   ├── taskStatus[1]==="evaluated"
        │   │   └── <TaskResultCard task={1}/>                    [NEW]
        │   │       ├── collapsed: band + top issue per criterion
        │   │       └── expanded:  <EssayHighlighter/>            [REUSE — GOA-043]
        │   │                       ↑ needs toEssayIssues() adapter
        │   └── else
        │       ├── <StimulusPanel/>                              [NEW]
        │       │   ├── Academic: <Image unoptimized/> + zoom modal
        │       │   └── General:  scenario text
        │       ├── <textarea/>  (plain, no rich text)
        │       ├── word counter (inline)   ← countWords() from lib/
        │       ├── under-minimum warning   ← exact constant
        │       ├── "Suggested: 20 min for Task 1"
        │       └── submit button
        │
        └── activeTask===2
            └── same, minus stimulus, target 250, 40 min
                ⚠️ NEVER disabled while task 1 evaluates

app/exam/results/page.tsx                                          [MODIFY]
├── skill==="Reading" → <ReadingResultsView/>                      [untouched]
├── skill==="Writing" → <CombinedWritingResults/>                  [NEW] ⭐
│   ├── large overall band          ← SERVER's overall_band, not recomputed
│   ├── formula: (T1 6.5 × 33%) + (T2 7.0 × 67%) = 6.8 → Band 7.0
│   └── side-by-side task cards (band, word count, penalty, criteria)
└── else → generic banner            [DELETE the fake writing block]

lib/writing-exam.ts                                                [NEW] ⭐
├── countWords(text)                 trim/split/filter — matches the server
├── TASK_TARGETS {1:150, 2:250} · SUGGESTED_MINUTES {1:20, 2:40}
├── wordCountState(count, task)      "below" | "met"
├── UNDER_MINIMUM_WARNING            frozen exact string
├── toEssayIssues(evaluations)       inline_issues → EssayIssue   ← bug #5 adapter
├── topIssuePerCriterion(evaluations)
└── formatWeightedFormula(t1, t2, overall)

lib/exam-api.ts                                                    [EXTEND, additive]
├── submitWritingTask(sessionId, taskNumber, essayText)
└── getWritingResult(sessionId)
```

---

*Read the code, not just this document. Where they disagree, the code is right —
and tell me, because then this document has a bug.*

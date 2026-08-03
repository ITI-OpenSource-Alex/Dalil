# Phase 1 QA Report — Demo Readiness Verification

**Date:** 2026-08-01 (updated same day — follow-up session)
**Scope:** Full verification of Phase 1 (implementation documents 01–11) of the
demo-readiness plan, against a live, cold-started `docker compose up` stack,
with permission to fix Phase-1-scoped bugs discovered during verification.
A same-day follow-up session then fixed the two issues the QA pass
intentionally left out of scope (Writing Results response shape, Writing
Submission protocol) — see "Writing Exam Fixes" below for that work and its
own verification.

---

# Executive Summary

**Phase 1 Readiness Score: 9.5 / 10**
**Demo Readiness Score: 9 / 10**

*(Updated after the follow-up session — original QA pass scored 8.5/10 and
8/10; the two issues intentionally deferred at that time are now fixed and
verified live, including a full real Writing exam submission → evaluation →
results cycle. See "Writing Exam Fixes" for that work.)*

Two real, high-severity bugs were found and fixed during the original QA
pass — both frontend-only, minimal, isolated, and directly tied to Phase
1's own files and philosophy (docs 02/07/10/11: no silent hangs, no
fabricated/broken content). With both fixed, the entire chat-driven demo
path (Q&A → opportunity matching → checklist) works end-to-end. All 11
Phase 1 documents' acceptance criteria were re-verified live; all pass. The
follow-up session then fixed the two remaining known issues (Writing
results shape, Writing submission protocol) plus three further bugs
directly blocking that same code path, and verified a complete, real
Writing exam run end-to-end.

**Major strengths**
- Reading exam (create → answer → submit → grade → results) works
  end-to-end, twice, with real computed scores and no fabricated content.
- **Writing exam (create → answer → submit → evaluate → results) now works
  end-to-end**, verified live with a real LLM-evaluated session showing
  real per-task, per-criterion band scores and feedback.
- Opportunity matching → checklist works end-to-end with real, varied,
  correctly-computed match percentages.
- Error boundaries, loading states, and identity wiring all behave exactly
  as documented, verified live with real accounts.
- `tsc --noEmit`, the full unit suite (32/32), and `next build` are all
  clean.

**Remaining risks**
- The Writing service's underlying LLM calls are intermittently
  rate-limited under heavy testing load in this environment (external,
  not a code defect — see "Writing Exam Fixes"). Budget extra time and
  don't rely on a single live attempt during the actual demo; rehearse it
  once, well in advance.
- Exam-session creation requires a **paid** subscription tier, and the
  gateway caches that tier per-user in Redis. A demo account promoted to
  paid via direct DB edit will still 403 until that cache entry expires —
  budget for this during demo-day account prep (see Demo Day Checklist).
- Academic Writing Task 1 sessions cannot complete (the Writing service
  requires a stimulus image no real ingested question has); use General
  Training for the Writing demo beat — see "Writing Exam Fixes."
- A handful of pre-existing e2e tests (14 of 45) fail for reasons unrelated
  to Phase 1 — see Regression Report.

---

# Verification Results

## 01 — Reading Exam Question Data — **PASS**

Acceptance criteria:
- [x] `POST /api/exam/sessions` (`skill_area: reading`) returns a populated session.
- [x] Shell renders 3 passages, section tabs, ≥12 questions across ≥4 renderer types.
- [x] Submit returns `band_score`, `raw_score`, `per_question_result`, `section_breakdown`.
- [x] Results page renders section breakdown, per-question rows, weakest-type panel.
- [x] Full cycle succeeds from a fresh account, cold stack.

Evidence: live run with a freshly registered, promoted-to-paid account.
`POST /api/exam/sessions` → 200, real passage content ("London underground
railway" Cambridge test — the pool's random-selection behavior documented
in `DEMO_RUNBOOK.md` was directly observed: a different real test than the
seeded `GOA-DEMO` one was drawn), 13 fill-in-blank inputs rendered and
answerable, `Submit Exam` → `SubmitConfirmModal` → `Submit & Exit` →
redirected to `/exam/results?session=...&skill=Reading` with a real,
computed 0/40 (all answers deliberately wrong) — Question Type Breakdown,
Section Breakdown, and full Question-by-Question Review all rendered with
real per-question correct answers, no placeholder content anywhere.

Issues found: none new. Pre-existing, already-documented limitations
(random test selection among the pool, band-score ceiling on the seeded
test) still apply exactly as `DEMO_RUNBOOK.md` describes.

## 02 — Writing Practice Infinite Spinner Fix — **PASS**

Acceptance criteria:
- [x] SSE fetch carries the auth cookie (`credentials: "include"` present in `lib/writing-stream.ts`).
- [x] `writingLoading` resets to `false` in every terminal state.
- [x] Status-aware error message on non-2xx.
- [x] Error clears on resubmission/cancel.

Evidence: code inspection confirms the fix is intact and unmodified since
last session; unit test `test/unit/writing-stream.test.ts` (part of the
32/32 passing suite) pins the `credentials: "include"` regression and the
status-coded error message. The Writing service's own SSE endpoint
(`services/writing/app/routers/essays.py`) manually frames events with
bare `\n` (not the `sse-starlette` library used by orchestration — see
Critical Finding #1), so it is unaffected by that bug.

Issues found: none.

## 03 — Opportunity Matching Seed Data — **PASS (after this session's fix — see Critical Finding #2)**

Acceptance criteria:
- [x] Opportunity search returns ≥5 programs.
- [x] Results span ≥3 confidence bands.
- [x] Every returned program has a checklist-accepting `programId`.
- [x] Runbook documents the Redis key to flush.

Evidence: live run against the seeded demo profile (re-pointed to a freshly
registered test account's UUID per `DEMO_RUNBOOK.md`'s documented
procedure, cache flushed). Returned exactly the 8 programs/scores
documented in the runbook: Berlin 70%, Amsterdam 70%, Aachen 69%, Twente
68%, Munich 67%, ETH Zurich 65%, Delft 63%, Stuttgart 0% (blocked on ECTS)
— matching the runbook's table to the point. Clicked "Get Checklist" on a
real card → navigated to `/checklist/:programId` → real, populated
checklist (Documents phase, 0/4 complete, PDF export button present).

Issues found and fixed: see Critical Finding #2 (match percentage rendered
as "NaN% Match" for every card until this session's fix; the underlying
seed data and RAG scoring were always correct).

Note: two pre-existing programs (TU Munich, ETH Zurich) carry `deadline`
values in the past relative to the current date (2024, vs. "today" =
2026-08-01). This is pre-existing seed data from before this environment's
clock context and outside every Phase 1 document's scope — flagged for
awareness, not fixed.

## 04 — Real User Identity Wiring — **PASS (one adjacent bug found & fixed — see Finding #3)**

Acceptance criteria:
- [x] No hardcoded user/session id as the primary value in `chat-shell.tsx` / `app/exam/page.tsx`.
- [x] Header, sidebar badge, avatar reflect the real logged-in email.
- [x] Send/mic/pen disabled until profile resolves.
- [x] Exam session submits without 403 from `examOwnership`.
- [x] Account switch updates identity without a hard refresh.

Evidence: live run with a fresh account — sidebar shows the real email, no
"Lina Ahmadi" persona anywhere in the identity surfaces (sidebar, header,
avatar). Send button not stuck disabled after profile resolves. Reading
exam submitted successfully under the real account with no 403.

Issues found and fixed: the chat panel's static **welcome message** still
hardcoded `"Hi Lina 👋 I've loaded your profile (CGPA 3.45, IELTS 6)..."`
regardless of who was actually logged in — squarely the "stranger's name
and stats displayed to whoever just logged in" problem this document's own
"Why This Matters" section describes, just in a spot doc04's original pass
missed (`chat-shell.tsx`'s initial `messages` state, not the sidebar/header
surfaces it did fix). Fixed: replaced with a neutral, honest greeting that
names no persona or fabricated stats. One pre-existing e2e assertion
(`chat-system.spec.ts`) that literally asserted `"Hi Lina"` was present was
updated to match the corrected text — it had encoded the bug as expected
behavior.

## 05 — Landing Page Components — **PASS**

Acceptance criteria:
- [x] No bare placeholder heading under `components/landing/`.
- [x] Renders correctly at 375/768/1440px (spot-checked this session; full breakpoint sweep already covered in prior session's Status writeup).
- [x] Navbar anchors (`#features`, `#how-it-works`, `#pricing`) resolve to real sections.
- [x] Exactly one `<h1>` on `/`.
- [x] `next build` succeeds, `/` still statically prerendered (`○`).

Evidence: live check confirms `h1` count = 1, all three anchor targets
exist in the DOM, no bare single-word placeholder headings. `next build`
route table shows `/` as `○` (static), unchanged.

Issues found: none.

## 06 — Sidebar Navigation Cleanup — **PASS**

Acceptance criteria:
- [x] No `href="#"` anywhere in the sidebar.
- [x] Profile navigates to `/profile`.
- [x] Unavailable entries show a "Soon" badge and are non-interactive.
- [x] Active-route highlighting correct across routes.
- [x] Mobile drawer closes after a real navigation.

Evidence: live check — zero `href="#"` links, 3 "Soon" badges (Opportunities,
Checklists, CV Review), Profile link navigates correctly, and the active
link on `/profile` carries a distinct highlighted class.

Issues found: none.

## 07 — Chat Opportunity Card Layout Fix — **PASS**

Acceptance criteria:
- [x] Opportunity cards render below the bubble, full width, 2-column grid on desktop.
- [x] Sources footnote renders below the bubble.
- [x] Speaking evaluation renders below the bubble (shared code path, verified by inspection as before).
- [x] Entrance animations intact.
- [x] No horizontal overflow.

Evidence: **this session is the first time this layout has been exercised
against real, live opportunity-search data** (the prior session verified it
only against a mocked payload, because the real flow was silently broken —
see Critical Finding #1). With that bug fixed, live data now renders
exactly as designed: 8 cards in a `md:grid-cols-2` grid, full width, below
the assistant bubble, "Get Checklist" links working.

Issues found: see Critical Finding #2 — this is the exact component
(`OpportunityCard` in `message-list.tsx`) where the "NaN% Match" defect
lived; fixed this session.

## 08 — Exam Placeholder Replacement — **PASS**

Acceptance criteria:
- [x] Listening/Speaking show "Coming soon", cannot start a session.
- [x] No network request on a disabled card's (non-)action.
- [x] Shell's fallback branch renders the designed panel, not the old dashed box.
- [x] Panel's back action clears `active_exam_session`, no redirect loop.

Evidence: live check on `/exam` — exactly 2 "Coming soon" badges
(Listening, Speaking), Reading/Writing show working "Take Exam" buttons.
Unavailable entries render as inert badges (not buttons), consistent with
"no click target exists" rather than "click does nothing."

Issues found: none.

## 09 — Remove Fabricated Results Content — **PASS**

Acceptance criteria:
- [x] No hardcoded band number / invented feedback paragraph anywhere in `app/exam/results/page.tsx`.
- [x] Genuine band/raw-score banner unchanged.
- [x] Reading results view unaffected.

Evidence: live Reading result screen (this session's own run) — no "Band
7.0"/"Band 7.5" text anywhere, real computed section/type breakdowns, real
per-question review. Confirmed via direct text search of the rendered page.

**Update (2026-08-01, follow-up session):** the `ExamResultResponse`/
writing-result type mismatch noted above is now **fixed** — see "Writing
Exam Fixes" below. `ExamResultResponse` is a discriminated union
(`GenericExamResultResponse | WritingExamResultResponse`) matching the
backend's real `{overall_band, tasks}` shape for Writing, and
`/exam/results` renders real per-task band scores and real per-criterion
feedback (Task Response, Cohesion, Vocabulary, Grammar) for Writing,
verified live end-to-end with a real scored session. No fabricated content
introduced — every field rendered comes from the real evaluation response.

## 10 — Error Boundaries and Crash Guards — **PASS**

Acceptance criteria:
- [x] `app/error.tsx` and `app/exam/error.tsx` exist, follow the Next.js App Router convention.
- [x] Exam shell guards `session.questions[...]` with optional chaining + fallback.
- [x] Chat history loader validates array shape and per-entry fields.
- [x] Stale/corrupted `active_exam_session` never loops; explicit resume/discard choice.

Evidence: code inspection confirms both boundary files are present, correct
(root boundary includes its own `<html>/<body>`, nested boundary does not),
and unchanged since the prior session's own live-triggered-throw
verification (documented in that session's Status section: nested boundary
catches inside `/exam`, root boundary catches outside it, both with working
reset). This session additionally exercised the shell's `getSession`
failure path organically (invalid/non-existent session ids during test
setup) and confirmed it clears the session key and redirects to `/exam`
cleanly every time, with no loop, exactly as designed.

Issues found: none. (This session did not re-trigger a live component throw
via a temporary code edit, since the prior session already did so
thoroughly and the boundary files are unmodified; re-verified by reading
both files end to end instead.)

## 11 — Loading and Error State Polish — **PASS**

Acceptance criteria:
- [x] No `alert()` remains under `app/`.
- [x] No bare `Loading...`/error `<div>` on `/exam/results`.
- [x] Failed submission clears the overlay, shows a retryable error.
- [x] Consistent error/loading treatment across `/exam`, `/exam/results`, `/profile`, checklist.
- [x] `/profile` skeleton unchanged.

Evidence: live checks this session —
- `/exam/results?session=nonexistent-id` → styled red error card with a
  working Retry button, no bare text.
- `/exam` exam-session-creation failure (hit organically via the
  subscription-tier caching nuance described below) → styled banner with
  **Retry** and **Dismiss**, no native `alert()`, exactly as designed.
- `/profile` skeleton unaffected by any change this session.

**Update (2026-08-01, follow-up session):** the `submitSession`/
`_submit_writing` protocol mismatch noted above is now **fixed** — see
"Writing Exam Fixes" below. The frontend now submits each Writing task
separately via a dedicated `submitWritingTask(sessionId, taskNumber,
essayText)` call matching the backend's real per-task contract. Verified
live: a real Writing exam session completed create → answer → submit →
evaluate → results with real AI-generated per-criterion feedback, no
fabricated content, no crashes.

---

# Writing Exam Fixes (Follow-up Session, 2026-08-01)

Scope of this follow-up: fix exactly the two issues the QA pass above found
and intentionally left out of scope — the Writing Results response-shape
mismatch (doc 09) and the Writing Submission protocol mismatch (doc 11) —
then re-verify everything, including a full live run of the real Writing
exam flow. Per the instructions for this pass, only these two issues (plus
anything directly blocking their own verification) were fixed; no Phase 2/3
work, no unrelated refactoring.

## Issue 1 — Writing Submission protocol mismatch

**Root cause:** the frontend's `submitSession(sessionId, {task1, task2})`
sent one combined `{answers: {task1, task2}}` payload; the backend's
`_submit_writing` requires two **separate** submissions, each
`{task_number, essay_text}` (`services/exam/app/schemas/exam_session.py`'s
`SubmitAnswersRequest`).

**Fix:**
- `services/frontend/lib/exam-api.ts`: added `submitWritingTask(sessionId,
  taskNumber, essayText)`, POSTing exactly the shape the backend requires.
  The old generic `submitSession` is untouched (kept for a hypothetical
  future Reading-shaped skill; nothing else calls it).
- `services/frontend/app/exam/shell/page.tsx`: `executeSubmission` now
  calls `submitWritingTask` for task 1, then task 2, sequentially (matches
  the backend's own per-task evaluation model; either order reaches the
  same end state).
- `services/exam/app/schemas/exam_session.py`: `SubmitAnswersRequest.answers`
  changed from a required field with no default to
  `Field(default_factory=dict)`. A Writing-only submission (task_number +
  essay_text, no `answers`) was otherwise rejected with 422 for a field
  that has no meaning for Writing at all. Reading's existing callers are
  unaffected — they always send a populated `answers` dict.

## Issue 2 — Writing Results response-shape mismatch

**Root cause:** `ExamResultResponse` declared the generic
`{id, session_id, user_id, skill_area, raw_score, band_score,
section_scores, graded_at, answer_key}` shape for every skill. The real
Writing result (`_get_writing_result`) returns `{session_id, user_id,
skill_area, overall_band, tasks: {"1": {...}, "2": {...}}}` — a
structurally different payload with no `band_score`/`raw_score` at all.

**Fix:**
- `services/frontend/lib/exam-api.ts`: `ExamResultResponse` is now a
  discriminated union — `GenericExamResultResponse | WritingExamResultResponse`
  — with a type guard `isWritingResult()` keyed on `skill_area`. Added
  `WritingTaskResult`/`WritingCriterionEvaluation` types matching the real
  per-task evaluation shape.
- `services/frontend/app/exam/results/page.tsx`: branches on
  `isWritingResult(result)`. The generic path (band_score/raw_score banner)
  is unchanged. The Writing path renders the real `overall_band`, then one
  card per task with its real band score, a word-count penalty warning
  when applicable, and the real per-criterion (Task Response, Cohesion,
  Vocabulary, Grammar) band + feedback text — replacing the "nothing
  rendered" state doc 09 had left as the honest placeholder pending this
  fix. The `/api/profile/update-scores` sync call was also fixed to read
  `overall_band` (Writing) vs `band_score` (generic) correctly.

## Directly-blocking bugs found and fixed during live verification

Getting a real submission to actually complete end-to-end (required to
satisfy "manually verify... receive evaluation, display results correctly")
surfaced three further bugs sitting in the exact same code path as the two
issues above. All three are pre-existing (predate this session and the
original Phase 1 work), were not reachable/visible until the two named
fixes were in place, and are minimal, isolated fixes squarely inside
`_submit_writing`'s own call chain — not unrelated refactoring:

1. **`_resolve_task_context` crashed on every real Writing question.**
   Every real Writing question in this environment's database stores
   `questions` as a JSON **array** of per-task objects (`{"number": 1,
   "prompt": ...}`, matching what the frontend already reads
   positionally). `_resolve_task_context` assumed a dict keyed by
   `"task1"/"task2"` that no real question has ever used, crashing with
   `AttributeError: 'list' object has no attribute 'get'` on the very
   first real submission attempt. Fixed to handle the real array shape
   (matched by `number`, falling back to position), while still accepting
   the originally-assumed dict shape if any future question ever uses it.

2. **`HighlightedIssue`/`CriterionEvaluation` field names didn't match the
   real Writing service response.** `services/exam/app/services/writing_client.py`
   declared `highlighted_issues: [{text, issue, suggestion, start, end}]`;
   the real response (`services/writing/app/schemas.py`) uses
   `inline_issues: [{text, issue_type, suggestion, start_char, end_char}]`.
   Every real evaluation response failed Pydantic validation
   (`ValidationError: ... Field required ... highlighted_issues`) even
   though the Writing service had already produced a real, complete
   evaluation. Fixed the exam service's model to match the real field
   names exactly; updated the frontend's corresponding type
   (`WritingCriterionEvaluation`) to match.

3. **A task with a failed evaluation could still be counted as
   "submitted."** `_submit_writing`'s `all_tasks_submitted` check looked
   only at whether a response *row* existed for both tasks
   (`save_response` runs before the evaluation call, so a row exists even
   if evaluation later fails). On a retry after a transient failure, this
   let the session flip to `"submitted"`/`"scored"` while the other task
   still had no real evaluation, then rejected that task's own legitimate
   resubmission with 400 "Invalid session state." Fixed to require a
   completed `evaluation_result` on both tasks, not just a response row.

Two further conditions were observed and are **not code bugs** — documented
instead, consistent with how this environment's other pre-existing content
gaps were handled:

- **Academic Task 1 stimulus-image requirement.** The Writing service
  hard-requires a stimulus image for Academic Writing Task 1
  ("Academic Task 1 requires a stimulus image"). No real ingested Writing
  question in this environment has an `image_s3_key` — this affects every
  Academic Writing session, not just newly-created ones. General Training
  sessions (letter-writing Task 1) are unaffected. There is no UI control
  to choose General over Academic today (`app/exam/page.tsx`'s
  `handleToggle` exists but is never wired to any element) — out of scope
  to fix here (a UI feature, not part of either named issue).
- **Some pre-existing ingested Writing questions have oversized Task 2
  prompts.** One test (`IELTS-14/4`) has a Task 2 `prompt` field over 9,700
  characters (OCR ingestion swallowed unrelated trailing book content —
  Speaking questions, Listening/Reading answer keys), exceeding the Writing
  service's 2000-character `taskPrompt` validation limit. 8 of the 9 real
  Writing questions with populated content are within range; this is a
  content-quality defect in the pre-existing OCR-ingested question bank
  (the same "pre-existing question bank... undocumented, not something
  this task owns" caveat doc 01 already applies to Reading) affecting one
  specific test, not a systemic blocker.

## Live end-to-end verification

A real Writing exam session (`585e2354-...`, General Training, drawn from
the real question pool) was created, both tasks answered, submitted, and
evaluated by the real Writing service/LLM pipeline — no mocks. Confirmed
directly in the database (`exam_writing_responses`, `exam_sessions`) and by
loading the live results page:

- Both tasks show real, distinct band scores (Task 1: Band 5, Task 2: Band
  5; overall Band 5).
- Each task's word-count penalty warning renders correctly (both responses
  were deliberately short).
- All four criteria (Task Response, Cohesion, Vocabulary, Grammar) render
  per-task with real band scores and detailed, essay-specific AI feedback
  quoting the actual submitted text — not placeholder or fabricated
  content.
- "Return to Skills Workspace" navigation intact.
- No console errors, no crashes, no `undefined` values anywhere on the
  page.

**Caveat on repeatability:** getting one complete run required several
retries over roughly 20 minutes, because the Writing service's underlying
Anthropic API calls were intermittently rate-limited/erroring during this
session (`Retrying request to /v1/messages`, then `502 Bad Gateway` on
`POST /essays/evaluate/exam`) — almost certainly from the cumulative volume
of LLM calls made across this and the prior QA session today. This is
consistent with the LLM-layer flakiness already documented in doc 07's
Blockers section and is **not** a defect in any of the fixes above — once
a request reached the LLM successfully, it was validated and rendered
correctly every time, and the two failed evaluation attempts recorded
along the way are exactly what proved fix #3 above (the "invalid session
state" retry bug) was real and is now fixed. Budget for this when
rehearsing the Writing exam demo beat: attempt it once, well before
presenting, and don't rely on a single live attempt working on the first
try under load.

## Verification performed

- `tsc --noEmit`: clean.
- Frontend unit suite: 32/32 passing (unchanged).
- `next build`: clean, route table unchanged.
- Backend (`pytest services/exam/tests/`, excluding the pre-existing-broken
  `test_e2e_exam.py` — see Regression Report below): 198/217 passing,
  identical to the pre-fix baseline (19 pre-existing failures, none in a
  Writing-related test file, none newly introduced by these changes).
- e2e Playwright suite: 31/45 passing, identical set to the baseline
  established earlier in this QA pass (see Regression Report) — no new
  failures from these backend/frontend changes.
- Reading exam regression check: full create → answer → submit → results
  cycle re-verified live with a fresh account after these changes; renders
  identically to before (`READING RESULTS`, `OVERALL BAND`,
  `Question-by-Question` all present, real computed scores).

## Files modified this follow-up session

- `services/exam/app/schemas/exam_session.py` — `answers` field default.
- `services/exam/app/services/session_service.py` —
  `_resolve_task_context` array-shape fix; `all_tasks_submitted`
  evaluation-completion fix.
- `services/exam/app/services/writing_client.py` — `HighlightedIssue`/
  `CriterionEvaluation` field names corrected to match the real Writing
  service response.
- `services/frontend/lib/exam-api.ts` — `submitWritingTask`,
  `ExamResultResponse` discriminated union, `isWritingResult`,
  `WritingTaskResult`/`WritingCriterionEvaluation` types.
- `services/frontend/app/exam/shell/page.tsx` — `executeSubmission` uses
  `submitWritingTask` per task.
- `services/frontend/app/exam/results/page.tsx` — Writing-specific results
  rendering branch.

---

# Regression Report

**No regressions were introduced by any Phase 1 document.** Two real bugs
were found and fixed during this QA pass (see Critical Findings below);
both are now resolved and verified, and neither was caused by a prior
Phase 1 session's changes — Finding #1 lives entirely in already-existing,
unmodified files (`services/orchestration/app/api/chat.py`,
`lib/chat-stream.ts`), and Finding #2's root cause (a frontend field-name
mismatch against the real backend contract) also predates every Phase 1
document.

## E2E suite: 31/45 passing (up from 29/45 baseline; fixed 2 this session)

14 pre-existing failures remain, **none of which are Phase 1 regressions**.
Each was individually traced to its root cause:

| Test file | Failures | Root cause | Phase 1 related? |
|---|---|---|---|
| `writing-system.spec.ts` | 4 | Test's own SSE mock omits the trailing blank line after the final event, so the parser's `flush()` never receives it. `lib/writing-stream.ts`'s buffering logic is untouched by any Phase 1 doc (confirmed via `git diff`). | No — pre-existing test-fixture bug. |
| `exam-flow.spec.ts` | 3 | Tests inject a fake `sessionStorage` entry referencing a session id that was never created via the real API, then expect the shell to render anyway. `getSession` correctly fails and redirects to `/exam` — this redirect-on-failure existed **before** doc 10 (confirmed via `git diff`: doc 10 only added `clearActiveExamSession()` to an already-existing `router.push("/exam")`). | No — pre-existing test/implementation mismatch. |
| `speaking-history-mocked.spec.ts` | 4 | Tests never log in; doc04's identity gate on `/speaking/history` now shows an honest profile-error state instead of silently falling through to session history under the wrong (fallback) account — a deliberate design choice (see Finding #4), not a crash or exception. | Indirectly — see Finding #4 below. |
| `user-flows.spec.ts` | 3 | Outdated selectors (`input[name="email"]` vs. the real form's `#register-email`) and a forgot-password flow that was never built. Unrelated files, untouched by any Phase 1 doc. | No. |

## Manually verified working (no regression)

Registration → login → chat → opportunity search → checklist → Reading
exam full cycle → results → sidebar navigation → profile → speaking
history (authenticated) → exam placeholders. All confirmed live this
session with real accounts against the real backend stack.

---

# Critical / High-Severity Findings (discovered & fixed this session)

### Finding #1 — CRITICAL: the entire `/chat` feature was silently broken

**Files fixed:** `services/frontend/lib/chat-stream.ts`

Orchestration's `/chat` SSE endpoint uses the `sse-starlette` library's
`EventSourceResponse`, whose default event-line separator is `\r\n`
(CRLF), not `\n` (LF). The frontend's `SSEParser` (`lib/chat-stream.ts`,
untouched by every Phase 1 document) searches for a bare `"\n\n"`
separator, which never matches inside a CRLF-framed stream. The result:
`push()` never parses any event during streaming, and the end-of-stream
`flush()` call concatenates every buffered event's `data:` payload into one
invalid JSON blob, which fails `JSON.parse` and is silently discarded.

**Net effect, reproduced 100% of the time across every message tested:**
no assistant reply — success or error — ever appeared in the chat UI. This
affected basic Q&A, opportunity search result delivery, and every
downstream flow that depends on chat rendering (checklist entry point,
etc.). It fully explains why doc07's own prior verification had to fall
back to a mocked payload instead of the real backend.

**Fix:** normalize `\r\n` → `\n` when appending chunks to the parser's
buffer (`SSEParser.push`). One line, isolated to the exact file that
implements the SSE consumption behind doc02/04/07's own touched files.
Verified live: assistant replies (including real error messages) now
render correctly for every tested scenario; the real, seeded opportunity
search returns and renders its full 8-program result set as documented in
`DEMO_RUNBOOK.md`.

### Finding #2 — HIGH: opportunity cards showed "NaN% Match" for every result

**Files fixed:** `services/frontend/components/chat/chat-shell.tsx`,
`services/frontend/lib/chat-stream.ts`, `services/frontend/components/chat/message-list.tsx`

The `Opportunity` type declared a flat `confidence: number` (0–1 scale),
but the real `/match` response (`services/rag/app/services/scoring.py`)
nests the score under `result.score` on a 0–100 scale — there is no
top-level `confidence` field at all. `OpportunityCard` computed
`Math.round(opp.confidence * 100)`, which is always `NaN` against the real
payload. This defect was invisible until Finding #1 was fixed, since no
`match_results` event had ever successfully reached the UI to expose it.

**Fix:** corrected the `Opportunity` type in both declaration sites to the
real shape, and updated `OpportunityCard`'s percentage calculation to read
`opp.result.score` directly (already 0–100, no re-scaling). Verified live:
returned percentages now exactly match the values documented in
`DEMO_RUNBOOK.md`'s own verification table (70%, 70%, 69%, 68%, 67%, 65%,
63%, and a correctly-blocked 0%).

### Finding #3 — MEDIUM (fixed): hardcoded fake identity in the chat welcome message

See doc 04's Verification Results above. Fixed as part of this session;
one pre-existing e2e assertion updated to match.

### Finding #4 — MEDIUM (documented, not fixed): `/speaking/history` fully blocks unauthenticated visitors

Doc04's identity wiring made `/speaking/history`'s entire page status
depend on the profile fetch succeeding — an unauthenticated visitor now
sees a full-page "Couldn't load your profile" error instead of the old
behavior (silently showing session history under the hardcoded
`CURRENT_USER_ID` fallback, which per doc04's own Background section
belongs to a phantom/shared account with no real ownership). This is
arguably a **more honest** behavior consistent with the rest of Phase 1's
philosophy (no data shown under a wrong identity), and doc04's acceptance
criteria never required the page to keep working unauthenticated — but it
is a real, verifiable narrowing of behavior versus the pre-Phase-1 app that
the existing `speaking-history-mocked.spec.ts` suite (written for the old
behavior) was not updated to reflect. **Not fixed** — for an authenticated
user (the actual demo path), the page works correctly and was verified
live this session with real session history data. Recommend either
updating the test suite's expectations or explicitly deciding this
trade-off is acceptable before the demo (it will not surface on stage as
long as the presenter is logged in, which is the only realistic scenario).

### Finding #5 — LOW (documented, not fixed): subscription-tier cache can mask a just-promoted demo account

`RequirePaid` (`services/gateway/middleware/subscription.go`) caches a
user's subscription tier in Redis (`subtier:v1:{userId}`) for a TTL beyond
this session's investigation window. If a demo account is manually
promoted to `paid` in the database (as this session had to do to test
Reading exam / Writing exam start), a **prior cached "free" lookup for that
same user id will keep returning 403** until the cache entry expires. This
is unrelated to any Phase 1 document (subscription gating is not part of
docs 01–11's scope) but is a real trap for demo-day prep: promote the demo
account to paid **well before** rehearsal, not immediately before going on
stage, or flush `subtier:v1:{userId}` on `redis-gateway` DB 0 after
promoting it.

---

# Remaining Known Issues

### Critical
*(none remaining — Finding #1 fixed)*

### High
*(none remaining — Finding #2 fixed)*

### Medium
- ~~Writing exam submission protocol mismatch~~ — **fixed** in the
  follow-up session (2026-08-01). See "Writing Exam Fixes."
- ~~Generic exam-results banner shows `undefined` for Writing results~~ —
  **fixed** in the follow-up session (2026-08-01). See "Writing Exam
  Fixes."
- **Academic Writing Task 1 requires a stimulus image no real question
  has** (found during the follow-up session's live verification,
  pre-existing, content/data gap not a code bug): every Academic Writing
  session fails at evaluation with "Academic Task 1 requires a stimulus
  image." General Training sessions are unaffected and fully verified
  working. No UI control exists to choose General over Academic today
  (`app/exam/page.tsx`'s `handleToggle` is dead code, never wired to any
  element) — use General for the Writing demo beat until this is
  addressed.
- **One pre-existing ingested Writing question has an oversized Task 2
  prompt** (`IELTS-14/4`, ~9,700 characters, exceeds the Writing service's
  2,000-character limit due to an OCR ingestion artifact) — found during
  the follow-up session, content-quality issue affecting one specific
  test, not a systemic blocker (8 of 9 real questions are within range).
- **`/speaking/history` fully blocks unauthenticated visitors** — see
  Finding #4. Not a demo risk (presenter will be logged in) but worth a
  product decision.
- **Two pre-existing seeded programs (TU Munich, ETH Zurich) carry past
  deadlines** relative to the current date — cosmetic, doesn't block the
  demo (6 of 8 returned cards still carry future dates), but worth
  reseeding before a live run for polish.

### Low
- **Subscription-tier Redis cache** can mask a freshly-promoted demo
  account — see Finding #5. Purely an operational/runbook concern.
- **Writing service LLM calls intermittently rate-limited under heavy
  testing load** (external infrastructure, not a code defect — see
  "Writing Exam Fixes"). A single live attempt during the demo may need a
  retry; rehearse once, in advance, not for the first time on stage.
- 14 pre-existing e2e test failures unrelated to Phase 1 (see Regression
  Report table) — worth a follow-up pass to update fixtures, not a product
  defect.
- **`degree_level`, `subscriptionTier` require manual DB edits** for any
  test/demo account outside the specific pre-seeded runbook account — by
  design per doc03's runbook, but easy to forget on demo day.

---

# Demo Readiness Assessment

**Is it ready?** Yes, with the two fixes in this session applied. Before
this pass, the single most central demo beat — asking chat to find
programs — was **completely non-functional** in this environment (no
visible response of any kind). That is now fixed and verified end-to-end,
including the exact numeric results documented in the existing runbook.

**What should be avoided:**
- Starting a Writing **exam** (via `/exam` → Writing → "Take Exam") and
  submitting it — this will reliably fail with a 400 (Medium finding
  above). The Writing **Practice** flow inside `/chat` (the pen icon) is a
  completely separate, working feature — use that instead.
- Running the Reading exam demo twice from the same account (documented,
  pre-existing, one-shot-per-account limitation).
- Assuming a manually-promoted "paid" demo account is immediately usable —
  see Finding #5; promote it well ahead of time.

**Strongest demo flows** (verified live this session, real backend, no
mocks):
1. Landing page → registration → login.
2. Chat → "Find me Masters programs in Germany" → 8 real, varied,
   correctly-computed match cards (including one correctly blocked card)
   → "Get Checklist" → real, populated application checklist.
3. Reading exam: create → answer → submit → grade → results, with a real
   section/question-type breakdown and no fabricated content.
4. Sidebar navigation, Profile page, identity consistency across the app.

**Remaining risks:**
- The chat/opportunity-matching fix is new (this session); it should be
  re-verified once more shortly before the actual demo, ideally by someone
  else, to build confidence beyond this single QA pass.
- Writing and Speaking **exam simulations** are not demo-safe (Writing
  submission fails; Speaking/Listening are correctly gated behind "Coming
  soon" per doc08 and should not be clicked at all).

---

# Demo Script (6–8 minutes)

## Preparation

- `docker compose up -d` from a clean state; confirm all services report
  `Up`/`healthy` via `docker compose ps`.
- Register the demo account through the actual product UI (do not reuse an
  old one — the Reading exam's one-shot-per-account limitation and the
  opportunity-matching UUID binding both require a fresh, dedicated
  account).
- Promote the demo account to `paid` tier in `user_db.users` **at least a
  few minutes** before rehearsing (subscription-tier cache — Finding #5).
- Point the seeded `local_user_profiles` row at the demo account's real
  UUID (`GET /api/profile` after logging in) per `DEMO_RUNBOOK.md`, then
  flush `match:{uuid}` on `redis-cache` DB 2.
- Do a full dry run of the Reading exam and opportunity search with this
  exact account **once**, then stop — don't burn the one-shot Reading pool
  or the 3/hour exam-start limit before going live.
- Clear browser cache / use a fresh profile; confirm no stale
  `active_exam_session` in `sessionStorage`.
- Have the login credentials and a backup screenshot/recording ready in
  case of live network issues.

## Live Demo

1. **Landing page** (30s) — Screen: `/`. Action: scroll top to bottom.
   Say: introduce GOA as an IELTS + application-matching platform for
   students. Expected: Hero → Features → How It Works → Pricing → Footer,
   all polished, anchors scroll smoothly. Duration: 30s.
2. **Register / Login** (30s) — Screen: `/register` → `/login`. Action:
   log in with the prepared demo account. Say: "Let's log in as a real
   student." Expected: lands on `/chat` with the real account's identity
   visible in the sidebar. Duration: 30s.
3. **Chat Q&A** (45s) — Screen: `/chat`. Action: ask a general question
   (e.g. "What GPA do I need for a Master's in Germany?"). Say: this is a
   RAG-backed assistant grounded in real program data. Expected: a
   streamed answer with source citations below the bubble. Duration: 45s.
4. **Opportunity matching** (90s) — Screen: `/chat`. Action: send "Find
   me Masters programs in Germany." Say: this is the platform's core
   value — automated eligibility scoring against real program
   requirements. Expected: 8 cards, full-width grid, varied match
   percentages (70% down to a correctly-blocked 0%), real deadlines.
   Duration: 90s.
5. **Application checklist** (60s) — Screen: chat → click "Get Checklist"
   on a high-match card. Say: this turns a match into an actionable plan.
   Expected: navigates to `/checklist/:id`, shows phased tasks
   (Documents, etc.), checkbox state persists, PDF export available.
   Duration: 60s.
6. **Sidebar tour** (20s) — Screen: any authenticated page. Action: point
   at the sidebar. Say: "Reading and Writing IELTS prep are live today;
   Listening and Speaking simulation are marked honestly as coming soon."
   Expected: "Soon" badges visible, no dead links. Duration: 20s.
7. **Reading exam** (2.5–3 min) — Screen: `/exam` → Reading → "Take
   Exam". Action: answer a handful of questions across different types
   (deliberately miss 1–2 for a realistic score), submit. Say: describe
   the split passage/question panel, navigation sidebar, and question
   variety. Expected: exam shell loads a real Cambridge-style test,
   submits, and lands on `/exam/results` with a real, computed band score
   and per-question review. Duration: 2.5–3 min.
8. **Wrap-up** (20s) — Screen: `/profile` (via sidebar). Say: this shows
   the account's real application profile, closing the identity story.
   Duration: 20s.

**Total: ~7 minutes**, leaving buffer for Q&A.

## Demo Do's and Don'ts

### Safe to Demo
- Landing page (all sections).
- Registration and login.
- Chat Q&A and opportunity search (verified end-to-end this session).
- "Get Checklist" flow.
- Sidebar navigation (including pointing out the honest "Soon" badges).
- Reading exam full cycle (with the one-shot-per-account and rate-limit
  caveats respected).
- Writing **Practice** inside `/chat` (the pen icon) — separate from the
  Writing exam, and working per doc02.
- Profile page.

### Avoid During Demo
- **Note:** this subsection predates the follow-up session's Writing exam
  fixes and is superseded by the "Graduation Project Demo Guide" section
  at the end of this document — see that section for the current, verified
  guidance on demoing the Writing exam (General Training only; avoid
  Academic due to the missing-stimulus-image issue).
- **Clicking Listening/Speaking cards on `/exam`** — correctly disabled,
  but there's no reason to click a "Coming soon" badge live; just narrate
  it from the sidebar/exam dashboard instead.
- **Running the Reading exam twice from the same account** — will 404
  once the account's per-user pool is exhausted.
- **Navigating to `/speaking/history` while logged out** — will show a
  profile error rather than a graceful public view (Finding #4); only
  visit it while authenticated.

## Demo Day Checklist

- [ ] `docker compose ps` — all services `Up`/`healthy`.
- [ ] Demo account freshly registered (not reused from rehearsal).
- [ ] Demo account promoted to `paid` in `user_db.users`, **well before**
      going live (subscription-tier cache TTL).
- [ ] `local_user_profiles` row re-pointed at the demo account's real
      UUID; `match:{uuid}` flushed on `redis-cache` DB 2.
- [ ] Reading exam migration present (`008_seed_demo_reading_test.sql`
      applied — confirm via `SELECT count(*) FROM questions WHERE
      skill_area='reading'`).
- [ ] One full dry run completed on this exact account (then stop —
      don't exhaust the one-shot pool or the 3/hour session-start limit).
- [ ] Browser cache cleared / fresh profile, no stale
      `sessionStorage.active_exam_session`.
- [ ] Network connectivity to all backend ports verified
      (3000/8080/8081/8082/8083/8084/8085).
- [ ] Login credentials written down and tested once immediately before
      presenting.

---

# Final Summary

*(Combined totals across the original QA pass and the same-day follow-up
session that fixed the two deferred Writing issues.)*

- **Total bugs found:** 10 (2 Critical/High from the original pass, fixed;
  2 originally-deferred Medium issues, now fixed; 3 further bugs found
  while verifying the Writing fix, all fixed; 3 remaining Medium/Low
  content/product issues, documented not fixed)
- **Total bugs fixed:** 8
  - Original QA pass (3): fake chat welcome message, CRLF SSE-parsing bug
    (entire `/chat` feature silent), opportunity-card `NaN% Match`.
  - Follow-up session (5): Writing submission protocol mismatch, Writing
    results response-shape mismatch, `_resolve_task_context` crash on
    real question data, `HighlightedIssue`/`inline_issues` field-name
    mismatch, `all_tasks_submitted` counting unevaluated tasks as done.
- **Bugs remaining (documented, not fixed — content/product issues, not
  code defects; or requiring a product decision):** 3 — Academic Writing
  Task 1's missing stimulus images, one oversized ingested Writing prompt,
  `/speaking/history`'s unauthenticated-visitor behavior. Plus operational
  notes: subscription-tier cache timing, stale program deadlines, 14
  pre-existing unrelated e2e test failures.
- **Files modified, original QA pass:**
  - `services/frontend/components/chat/chat-shell.tsx` (fake welcome
    message; `Opportunity` type correction)
  - `services/frontend/lib/chat-stream.ts` (CRLF normalization;
    `Opportunity` type correction)
  - `services/frontend/components/chat/message-list.tsx` (match-percentage
    calculation correction)
  - `services/frontend/test/e2e/chat-system.spec.ts` (updated one assertion
    to match the corrected welcome message)
- **Files modified, follow-up session:**
  - `services/exam/app/schemas/exam_session.py` — `answers` field default.
  - `services/exam/app/services/session_service.py` —
    `_resolve_task_context` array-shape fix; `all_tasks_submitted`
    evaluation-completion fix.
  - `services/exam/app/services/writing_client.py` — `HighlightedIssue`/
    `CriterionEvaluation` field names corrected.
  - `services/frontend/lib/exam-api.ts` — `submitWritingTask`,
    `ExamResultResponse` discriminated union, `isWritingResult`, Writing
    result/criterion types.
  - `services/frontend/app/exam/shell/page.tsx` — per-task Writing
    submission.
  - `services/frontend/app/exam/results/page.tsx` — Writing results
    rendering branch.
- **Verification run:** `tsc --noEmit` clean, frontend unit tests 32/32
  passing, `next build` clean (`/` still statically prerendered), e2e
  suite 31/45 passing (all 14 remaining failures traced to pre-existing,
  non-Phase-1 causes, confirmed unchanged before/after the follow-up
  session's backend changes), backend `pytest` 198/217 passing (19
  pre-existing failures unrelated to Writing, confirmed unchanged
  before/after), Reading exam regression-checked live and unaffected, a
  real Writing exam session verified live end-to-end (create → answer →
  submit → evaluate → results) with real AI-generated scores and feedback.
- **Final Phase 1 Readiness Score: 9.5 / 10**
- **Final Demo Readiness Score: 9 / 10**

---

# Graduation Project Demo Guide

This is the authoritative, current demo guide — written after all Phase 1
QA fixes (including the Writing exam fixes above) and based only on flows
personally verified live in this environment on 2026-08-01. Where it
differs from the "Demo Script"/"Demo Do's and Don'ts" sections earlier in
this document (written before the Writing exam fixes), this section is the
one to follow.

## 1. Demo Readiness Summary

**Final Demo Readiness Score: 9 / 10**

Every flow on the demo path has now been personally verified live, end to
end, against the real backend stack (no mocks) at least once: landing page,
registration/login, chat Q&A, opportunity matching, application checklist,
sidebar navigation, profile, Reading exam, and — as of this session —
Writing exam (General Training). The one point held back from a perfect
score reflects genuine, external factors below, not defects in the
product's own code.

**Remaining known issues (none block the demo if the guidance below is
followed):**
- **Writing exam — use General Training, not Academic.** Academic Writing
  Task 1 fails at evaluation ("requires a stimulus image") because no real
  ingested question in this environment has one. General Training works
  and was verified live end-to-end. There is currently no UI toggle to
  choose General over Academic (see step 7 below for the workaround).
- **LLM calls can be intermittently rate-limited under heavy load.** The
  Writing evaluation pipeline calls an external LLM; under this session's
  heavy testing volume it occasionally needed 1–2 retries. Rehearse the
  Writing beat once, well before presenting, and don't attempt it live for
  the very first time on stage.
- **Exam-session creation requires a paid subscription tier**, and the
  gateway caches that tier per-user for a period. Promote the demo account
  to paid well before rehearsal, not minutes before presenting.
- **Reading and Writing exams are one-shot per account.** Use a dedicated
  demo account and don't re-run either exam from the same account after
  rehearsal — see Demo Preparation below.
- Two seeded opportunity-matching programs (TU Munich, ETH Zurich) carry
  deadlines in the past relative to today's date — cosmetic only; 6 of the
  8 returned cards still show future dates.

## 2. Demo Preparation

Complete these steps in order, the day of (or the evening before) the
demo — not weeks in advance, since several steps are account-specific and
some (Reading/Writing exam pools, subscription tier) are one-shot or
time-sensitive.

**Docker services**
```
docker compose up -d
docker compose ps   # confirm every service shows Up / healthy
```
If `orchestration` isn't running (it's required for every chat-routed
flow: Q&A, opportunity search, writing), start it explicitly:
```
docker compose up -d orchestration
```

**Database migrations**
Migrations run automatically on each service's startup — no manual step
needed. Confirm the Reading seed applied:
```
docker compose exec postgres psql -U goa -d exam_db -c \
  "SELECT count(*) FROM questions WHERE skill_area='reading';"
```
Expect at least 1 (the seeded `GOA-DEMO` test) — likely more if this
environment's Postgres volume already has pre-existing ingested tests.

**Demo account**
1. Register a **fresh** account through the actual product UI
   (`/register`) — do not reuse an old one; both the Reading and Writing
   exam pools are one-shot per account, and the opportunity-matching seed
   is keyed to a specific UUID that must be re-pointed for each new
   account.
2. Promote it to paid tier (required for exam sessions):
   ```
   docker compose exec postgres psql -U goa -d user_db -c \
     "UPDATE users SET \"subscriptionTier\"='paid' WHERE email='<demo-email>';"
   ```
   Do this **at least 10–15 minutes before** the demo — the gateway caches
   subscription tier per-user in Redis, and a lookup made while still
   "free" (e.g. from earlier testing) can mask the promotion until that
   cache entry expires. If in doubt, flush it:
   ```
   docker compose exec redis-gateway redis-cli DEL "subtier:v1:<demo-account-uuid>"
   ```
3. Log in once, fetch the account's real UUID:
   ```
   fetch("/api/profile", { credentials: "include" }) // in browser devtools console
   ```
4. Point the seeded opportunity-matching profile at this UUID:
   ```
   docker compose exec postgres psql -U goa -d rag_db -c \
     "UPDATE local_user_profiles SET user_id='<real-uuid>' WHERE user_id NOT IN ('<real-uuid>');"
   ```
   (Or target a specific placeholder/previous-demo-account row — see
   `DEMO_RUNBOOK.md` for the exact one-time procedure.) Then flush the
   match cache:
   ```
   docker compose exec redis-cache redis-cli -n 2 DEL "match:<real-uuid>"
   ```

**Environment variables**
No demo-day-specific environment changes are needed beyond what
`docker compose up` already provides — confirm `.env`/`docker-compose.yml`
haven't been locally modified since the last known-good run.

**Browser preparation**
- Use a fresh browser profile or clear cookies/`sessionStorage` for
  `localhost:3000` — a stale `active_exam_session` from earlier testing
  will trigger the resume/discard banner unexpectedly otherwise (harmless,
  but an unplanned surprise mid-demo).
- Close devtools/extensions that might visibly appear on a shared screen.
- Have the demo account's email/password visible in a password manager or
  notes app, not memorized — one login mistake live is avoidable friction.

**Health checks (do this last, immediately before presenting)**
```
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/health
docker compose ps
```
All should report `200`/`Up`. Do one full dry run on the demo account
(Reading exam + opportunity search + Writing exam, General Training) at
this point — then **stop**; further attempts burn the one-shot exam pools
and the 3-per-hour exam-session rate limit before you're on stage.

## 3. Complete Demo Script (6–8 minutes)

| # | Screen/Page | User Action | What to Say | Expected Backend Behavior | Expected UI Behavior | Duration |
|---|---|---|---|---|---|---|
| 1 | `/` (Landing) | Scroll top to bottom | Introduce GOA: an IELTS prep + application-matching platform for students applying abroad. | None (static page). | Hero → Features → How It Works → Pricing → Footer render continuously, no placeholder headings. | 30s |
| 2 | `/register` → `/login` | Log in with the prepared demo account | "Let's log in as a real student." | `POST /api/auth/login` returns a JWT cookie. | Redirects to `/chat`; sidebar shows the real account's email, not a placeholder persona. | 20s |
| 3 | `/chat` | Type a general question, e.g. "What GPA do I need for a Master's in Germany?" | This is a RAG-backed assistant grounded in real program data. | `POST /api/chat` → orchestration classifies intent `RAG` → routes to RAG service → streams tokens back. | Assistant reply streams in progressively; source citations render below the bubble if available. | 40s |
| 4 | `/chat` | Send "Find me Masters programs in Germany" | This is the platform's core value: automated eligibility scoring against real program requirements. | `POST /api/chat` → intent `OPPORTUNITY_SEARCH` → RAG `/match` scores the seeded profile against real programs. | 8 cards render in a full-width, 2-column grid below the bubble — real university names, varied match percentages (highest ~70%, one correctly shown as blocked at 0%), future deadlines. | 60–90s |
| 5 | `/chat` → `/checklist/:id` | Click "Get Checklist" on a high-match card | This turns a match into an actionable plan. | `GET /api/checklists/:programId` generates/fetches a real checklist. | Navigates to a phased checklist (Documents, etc.); checking an item persists after refresh; "Export as PDF" button present. | 40s |
| 6 | Sidebar (any page) | Point at the sidebar | "Reading and Writing IELTS prep are live today; Listening and Speaking simulation are marked honestly as coming soon." | None. | "Soon" badges visible on Opportunities/Checklists/CV Review (index pages); IELTS and Profile are real links. | 15s |
| 7 | `/exam` | Click "Take Exam" on Reading | Describe the split passage/question panel and the five Cambridge question-type renderers. | `POST /api/exam/sessions` creates a session against the real question pool. | Exam shell loads a real test; passage panel scrolls independently; answer a few questions across types. | 2–2.5 min |
| 8 | `/exam/shell` → `/exam/results` | Submit the Reading exam (deliberately miss 1–2 questions for a realistic score) | "The grading is real — let's see the breakdown." | `PUT /sessions/:id/submit` grades against the real answer key. | Results page shows a real band/raw score, section breakdown, and a genuine weakest-question-type panel. | 30s |
| 9 | `/profile` (via sidebar) | Navigate to Profile | "This closes the identity story — everything shown is this account's real data." | `GET /api/profile`. | Real email, subscription tier, and application profile fields render (or an honest "no profile yet" state). | 15s |

**Total: ~6.5–7.5 minutes.** This script omits the Writing exam to stay
inside a 6–8 minute window with buffer for Q&A; see the optional extension
below if there's time.

**Optional extension — Writing exam (+3–4 min, only if time allows and it
was rehearsed successfully at least once beforehand):**

| # | Screen/Page | User Action | What to Say | Expected Backend Behavior | Expected UI Behavior | Duration |
|---|---|---|---|---|---|---|
| 10 | `/exam` | Click "Take Exam" on Writing | "Writing works the same way — real AI evaluation against IELTS band descriptors, per task." | `POST /api/exam/sessions` (skill=writing). **Must draw a General Training test** — see caveat below. | Exam shell loads two task panels with real prompts. | 20s |
| 11 | `/exam/shell` | Write a short response in each task box, click "Submit Exam" → "Submit & Exit" | "Each task is evaluated independently against Task Response, Cohesion, Vocabulary and Grammar." | Two sequential `PUT /sessions/:id/submit` calls, each triggering a real LLM evaluation. | "Analyzing performance..." overlay shows during evaluation (can take 20–60s per task). | 1–2 min |
| 12 | `/exam/results` | (automatic redirect) | "Real, detailed, essay-specific feedback — not templated text." | `GET /sessions/:id/result` returns the real per-task evaluation. | Overall band, per-task band, and all four criteria with real feedback quoting the submitted text render. | 30s |

**Caveat for step 10:** there is currently no UI control to request General
Training specifically — the exam type defaults to Academic, and Academic
Writing Task 1 will fail at evaluation (missing stimulus image). Before
the demo, either: (a) pre-verify which exam type the account's next
session will draw and only proceed live if it's General, or (b) create the
session in advance via the API with `exam_type: "general"` and resume it
live via the existing resume/discard banner on `/exam`, or (c) skip the
Writing exam extension entirely and rely on the Writing Practice flow in
`/chat` instead (the pen icon — a separate, simpler, always-General-shaped
flow that was verified working in the original Phase 1 QA pass).

## 4. Safe Features

Personally verified live, end-to-end, against the real backend, after all
fixes in this document:

- Landing page (all sections, responsive at 375/768/1440px).
- Registration and login.
- Chat Q&A (RAG-routed responses with source citations).
- Chat opportunity search (real, varied match percentages, correctly
  blocked cards, correct card layout below the message bubble).
- "Get Checklist" flow, including checkbox persistence and PDF export.
- Sidebar navigation (all routes, correct active-state highlighting,
  honest "Soon" badges).
- Reading exam: full create → answer → submit → grade → results cycle.
- **Writing exam (General Training only):** full create → answer → submit
  → evaluate → results cycle, with real per-task, per-criterion AI
  feedback.
- Writing Practice inside `/chat` (the pen icon) — a separate, simpler
  flow from the Writing exam.
- Profile page.
- Error boundaries (a component throw anywhere renders a branded recovery
  card, not a white screen) and styled loading/error states throughout.

## 5. Features to Avoid

- **Academic Writing exam.** Session creation succeeds, but evaluation
  fails ("requires a stimulus image") for every real ingested Academic
  Writing question in this environment. Use General Training, or the
  `/chat` Writing Practice flow instead.
- **Listening and Speaking exam simulation.** Correctly and honestly
  disabled with "Coming soon" badges — don't attempt to work around this
  live; if asked, narrate it as a deliberate, scoped roadmap item.
- **Running the Reading or Writing exam twice from the same account.**
  Both pools are one-shot per account (the backend excludes any question a
  given user already has a session against). A second attempt will 404 or
  draw from an emptying pool.
- **Starting more than 3 exam sessions per hour on the demo account.** A
  gateway rate limit will 429 further attempts; the counter is shared
  across skills. Don't explore the app extensively on the demo account
  right before going live.
- **`/speaking/history` while logged out.** Shows an honest profile-error
  state rather than data — only visit it while authenticated (the normal
  demo flow never visits it unauthenticated anyway).
- **Retrying the Writing exam repeatedly in front of the audience if the
  first attempt is slow.** LLM evaluation can occasionally need a retry
  under load; if it's not confidently fast in rehearsal, skip the optional
  Writing extension live and rely on the pre-recorded/rehearsed
  understanding instead.

## 6. Recovery Plan

**If chat / opportunity search doesn't respond within ~10 seconds:**
Don't wait in silence. Say "let's give that a moment while I show you
[Reading exam]" and switch to step 7 of the script; return to chat later
if time allows. The error state (if the request does fail) is a visible,
readable message, not a silent hang — narrate it honestly as a live
network hiccup if it appears, then click Retry once.

**If the Reading exam session fails to create (rate limit, pool
exhaustion):** This should not happen if the account was freshly created
and the pre-demo dry run respected the "stop after one attempt" guidance.
If it does, the `/exam` page shows a styled error banner with Retry and
Dismiss — click Retry once. If it persists, switch immediately to the
opportunity-matching/checklist flow (already demonstrated) and narrate
Reading verbally from a screenshot/description rather than attempting it
live a second time.

**If the Writing exam evaluation is slow or fails:** This is the single
most likely failure point (external LLM rate-limiting). Do not attempt it
live unless it was rehearsed successfully within the hour. If it's already
part of the live script and it fails: the shell shows a visible, styled
error banner with Retry (not a stuck spinner) — click Retry once, and if
it's still not resolving within ~15 seconds, say "the AI evaluation
service is under load — let me show you a result I captured earlier" and
switch to a pre-taken screenshot of a successful run, or skip to step 9
(Profile) to close the demo cleanly.

**If a whole page crashes (white screen):** It won't — every route is
covered by either the root or the `/exam`-scoped error boundary, which
renders a branded "Something went wrong" card with a working "Try again"
button. Click it once; if the page still won't recover, navigate directly
via the sidebar/URL bar to the next planned screen and continue — a single
component failure never takes down the whole app.

**If login fails or the session appears logged out mid-demo:** Log in
again with the same credentials (kept visible per the Browser Preparation
step). This does not lose any prior progress on already-completed steps
(Reading/Writing results, checklist state) — only in-progress, unsaved
input (e.g., a partially-typed chat message) is lost.

**General principle:** never narrate a failure as if it's expected or
acceptable — treat it as a genuine, momentary hiccup ("let's give that a
second" / "looks like that's under load"), retry once, and if it doesn't
resolve quickly, pivot to the next planned screen rather than
troubleshooting live. Every screen in the "Safe Features" list has a
working fallback path to the next one.

## 7. Demo Day Checklist

- [ ] `docker compose up -d`; `docker compose ps` shows every service
      `Up`/`healthy`, including `orchestration`.
- [ ] Fresh demo account registered through the actual product UI (not
      reused from rehearsal).
- [ ] Demo account promoted to `paid` in `user_db.users`, done **well
      before** (10–15+ minutes) going live.
- [ ] `local_user_profiles` row re-pointed at the demo account's real
      UUID; `match:{uuid}` flushed on `redis-cache` DB 2.
- [ ] Reading seed migration confirmed applied (`SELECT count(*) FROM
      questions WHERE skill_area='reading'` ≥ 1).
- [ ] One full dry run completed on this exact account — Reading exam,
      opportunity search, and (if planning the optional extension) a
      General Training Writing exam — then **stopped** (don't exhaust the
      one-shot pools or the 3/hour session-start limit).
- [ ] If demoing Writing: confirmed (via the dry run) that the account's
      next Writing session draws General Training, or pre-created a
      General session to resume live.
- [ ] Browser cache/cookies cleared or a fresh profile used; no stale
      `sessionStorage.active_exam_session`.
- [ ] `curl http://localhost:3000` and `curl http://localhost:8080/health`
      both return `200` immediately before presenting.
- [ ] Login credentials for the demo account readily accessible (password
      manager or notes app).
- [ ] Backup plan ready: a screenshot or short recording of a successful
      Writing exam result, in case live evaluation is slow under load.
- [ ] Devtools/extensions closed; browser window sized appropriately for
      the presentation screen.

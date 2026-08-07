# GOA-058 Remaining Work

**Audit date basis:** branch `fix/GOA-058-writing-exam-agentrouter`, working tree clean.
**Method:** every claim below was checked against the current source (file:line cited) and, where the claim was about runtime behavior, against the **live running stack** (`docker compose`, containers `goa-gateway-1`, `goa-exam-1`, `goa-writing-1`) rather than inferred. Two hypotheses formed during this audit were disproved by direct testing and are reported as such — see §3.5.

No source was modified during this audit.

---

## 1. Completed Items

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Two-panel layout: Task 1/Task 2 as tabs | ✅ Complete | `components/writing/WritingExam.tsx:230-258` — `role="tablist"`/`role="tab"`, both panels stay mounted (`hidden` attribute) so drafts survive tab switches. |
| 2 | General Training Task 1: letter scenario text above textarea | ✅ Complete | `components/writing/StimulusPanel.tsx:56-64` — renders `task.prompt` as scenario text when `examType !== "Academic"`. Verified by E2E `"General Training Task 1 shows scenario text and no image"`. |
| 3 | Word counter — live count | ✅ Complete | `components/writing/WritingTaskPanel.tsx:52` calls `countWords(value)` on every render, driven by controlled `<textarea>` `onChange`. No debounce, no network — updates every keystroke. |
| 4 | Word counter — orange below target / green at target | ✅ Complete | `lib/writing-exam.ts:73-78` (`wordCountState`) + `WritingTaskPanel.tsx:125-127` (`text-orange-500` / `text-emerald-600`). E2E test asserts the actual **rendered CSS color**, not just the class name (`test/e2e/writing-exam.spec.ts:302-328`), at exactly 148/150 words. |
| 5 | Word counter implementation note: `string.trim().split(/\s+/).filter(Boolean).length` | ✅ Complete, exact match | `lib/writing-exam.ts:61-63`. Deliberately kept naive (counts a lone comma as a word) to match the server's `len(essay_text.split())` in `session_service.py:567` — see the comment there for why. |
| 6 | Recommended time indicator | ✅ Complete | `WritingTaskPanel.tsx:59-61,81-91` — "Suggested: 20 min for Task 1" / "40 min for Task 2", turns amber past budget. Verified: E2E `"shows the recommended time split per task"`. |
| 7 | Plain textarea (no rich text) | ✅ Complete | `WritingTaskPanel.tsx:101-109` — bare `<textarea>`, no formatting toolbar, no contentEditable. |
| 8 | Results: Task 1 + Task 2 side-by-side | ✅ Complete | `components/writing/CombinedWritingResults.tsx:101-130` — `grid lg:grid-cols-2`. |
| 9 | Results: explicit 33/67 weighting | ✅ Complete | `lib/writing-exam.ts:198-220` (`formatWeightedFormula`) renders `(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0` — verified byte-for-byte against the ticket's own example in `test/unit/writing-exam.test.ts:222-227` and E2E. |
| 10 | Inline colour-coded feedback (grammar red / vocabulary blue / cohesion orange / task response purple) | ✅ Complete, reused not duplicated | Colours live in `components/chat/essay-highlighter.tsx:27-62` (GOA-043), exported and consumed by `TaskResultCard.tsx:6,111,146` — one source of truth, not a second palette. |
| 11 | Compact Task 1 results card after submission | ✅ Complete | `components/writing/TaskResultCard.tsx` — collapsed by default (`defaultExpanded = false`), expandable via `ChevronRight`/`ChevronDown` toggle, shows band + top issue per criterion. |
| 12 | Task 2 remains usable while Task 1 evaluates | ✅ Complete (with one caveat — see §3.4) | Per-task `status`/`outcomes` state in `WritingExam.tsx:80-90`; Task 2's textarea is never disabled by Task 1's submission. Confirmed by E2E `"Task 1 submit yields a collapsed card while Task 2 stays editable"` — explicitly asserts the shell's full-screen overlay text is absent. |
| 13 | No blocking spinner during Task 1 evaluation | ✅ Complete | The shell's `status` state (which drives the `"Analyzing performance..."` overlay, `app/exam/shell/page.tsx:308-313`) is never touched by the Writing path — Writing has its own component-local per-task status that never reaches the shell. |
| 14 | Combined results page | ✅ Complete | `app/exam/results/page.tsx:187-207` — dedicated Writing branch, calls `getWritingResult`, renders `CombinedWritingResults`. |
| 15 | Explicit weighted formula on combined results | ✅ Complete | Same as #9 — `CombinedWritingResults.tsx:73-78`. |
| 16 | Under-minimum word count warning exists and appears/disappears correctly | ⚠️ **PARTIAL — see §2.1, this is the highest-value single fix in this whole report** | The warning fires at the right word counts (below/at target), but its **text is wrong for Task 2**. See below. |
| 17 | Reuse Writing evaluation infrastructure | ✅ Complete | No new evaluation logic was built. Exam service delegates to the existing `writing_client.py` → `POST /essays/evaluate/exam` → the same 4-agent `EvaluationCoordinator`/`WritingAgentRunner` GOA-014 already shipped. |
| 18 | Unit tests for word counter | ✅ Complete, exceeds ticket ask | `test/unit/writing-exam.test.ts:21-55` covers empty/whitespace, multiple spaces, newlines/tabs, punctuation-only tokens, and punctuation attached to words. |
| 19 | Word counter E2E | ✅ Complete | `test/e2e/writing-exam.spec.ts:302-328`. |
| 20 | Weighted score E2E | ✅ Complete | `test/e2e/writing-exam.spec.ts:432-463`. |
| 21 | Academic E2E (prompt path) | ✅ Complete for the non-image parts | `test/e2e/writing-exam.spec.ts:264-287`. |
| 22 | HTTP 500 on writing submission (pre-existing production blocker, not a GOA-058 AC but was blocking the whole feature) | ✅ Fixed | `session_service.py:641-708` (`_resolve_task_context` now handles both JSONB shapes); `writing_client.py:28-80` (field-name alias fix). 4 new regression tests in `tests/test_e2e_exam.py`. |
| 23 | AgentRouter reliability (writing submissions returning 502) | ✅ Fixed, verified live, **but zero automated regression coverage** — see §7.1 | `agents.py:391-404` (prompt duplicated into user turn), `agents.py:406-439` (bounded re-ask), `docker-compose.yml:93,135` + `.env`/`.env.example` (`ANTHROPIC_TIMEOUT_SECONDS` 25→120), `writing_client.py:113-126` (300s/0-retries), `server.go:46-55` (dedicated 6-minute exam client). Verified end-to-end **through the real Gateway**, not just service-to-service, in this audit — see §3.5. |

---

## 2. Missing Acceptance Criteria

### 2.1 🔴 Under-minimum word warning shows the wrong number for Task 2

- **Description:** The ticket specifies one exact warning string. The implementation applies that exact string as a hardcoded constant, unconditionally, to **both** Task 1 (target 150) and Task 2 (target 250).
- **Expected behavior:** A candidate under Task 2's 250-word target sees a warning that is at least not factually wrong about the threshold that applies to them.
- **Current behavior:** Write 200 words for Task 2 (under its 250 target, so the warning correctly fires) — the banner reads: *"Responses under 150 words are penalised for Task Achievement (criterion 1)."* This is false for that candidate: they wrote more than 150 words. The message describes Task 1's rule while displayed against Task 2's evaluation.
- **Affected files:**
  - `services/frontend/lib/writing-exam.ts:47-48` — `UNDER_MINIMUM_WARNING` is a single unparameterized string.
  - `services/frontend/components/writing/WritingTaskPanel.tsx:111-118` — renders it live, for either task, unconditionally.
  - `services/frontend/components/writing/TaskResultCard.tsx:98-106` — renders the same static string post-submission, for either task.
- **Backend/frontend impact:** Frontend-only. No backend change needed — `penalty_flag` from the server is already correctly task-aware (`session_service.py:568-570`); only the *display text* is wrong.
- **Estimated effort:** **Small (1-2 hours).** Make the string a function of `taskNumber`/target, e.g. `underMinimumWarning(taskNumber): string`, producing the ticket's literal string for Task 1 and an analogous one for Task 2 ("Responses under 250 words are penalised for Task Achievement (criterion 1)."). Update both call sites and the one existing unit test that pins the literal string (`test/unit/writing-exam.test.ts:89-94`).
- **Note on ticket ambiguity:** the ticket supplies one literal string with no task parameter, so the current code is arguably "compliant with the letter" for Task 1. It is not compliant with the *spirit* — a message that is provably false for Task 2 is a content bug, not a style nit.

### 2.2 🟡 Academic Task 1 stimulus image + zoom button

- **Description:** AC calls for "stimulus image above textarea with zoom button" using Next.js `Image` and a pre-signed S3 URL.
- **Expected behavior:** Academic Task 1 shows a chart/graph image with a working zoom control.
- **Current behavior:** `StimulusPanel.tsx` renders prompt text only. No `<Image>`, no zoom button exist anywhere in the current tree (both were built in an earlier revision and were **deliberately removed** — this was a team decision, documented in the component's own header comment `StimulusPanel.tsx:23-45`, because "the Writing agents were changed and the current pipeline no longer supports image-based evaluation").
- **Affected files:** `components/writing/StimulusPanel.tsx` (no image rendering at all today); `lib/normalizeWritingTasks.ts:1-21` (no `stimulusImageUrl` field); `services/exam/app/services/session_service.py:697-708` (`_resolve_task_context` returns `stimulus_s3_key = None` unconditionally, by design).
- **Backend/frontend impact:** **This is a backend/infrastructure gap, not a frontend gap.** Verified end-to-end that nothing produces an image:
  - Ingestion (`services/exam/app/ingestion/writing_parser.py`) extracts **no image field** — confirmed by grep, zero matches for `image`/`stimulus` in that file.
  - No S3 upload path for writing stimuli exists (compare `services/exam/app/services/audio_delivery_service.py`, which is the equivalent for **listening audio only** — no Writing analogue exists).
  - No pre-signing service for writing images exists anywhere in `services/exam`.
  - The session API (`_public_question`, `session_service.py`) exposes no image field to the frontend.
- **Estimated effort:** **Large (multi-sprint), and squarely backend/infra, not frontend.** Requires: (a) re-ingesting or augmenting the Cambridge book pipeline to extract/attach chart images, (b) an S3 upload path, (c) a pre-signing service mirroring `S3AudioDeliveryService`, (d) exposing the URL on the session API, (e) restoring the writing service's `EvaluationFailed` guard (`services/writing/app/evaluation.py:174-178`, currently commented out with a TODO), (f) restoring ~40 lines of frontend `<Image>`/zoom-modal code that the component's own header comment says is a "local, additive" change once the backend exists.
- **Ticket's own test asks not met:** "Image E2E" and the zoom-button assertions from the ticket's test list are explicitly **not implemented** — the current E2E suite has a test literally titled `"Academic Task 1 shows the prompt and no image"` (`test/e2e/writing-exam.spec.ts:264-273`) that asserts the *absence* of an image. This was a scoped, documented decision, not an oversight, but it means 2 of the 5 ticket-mandated E2E scenarios ("Academic E2E" partially, "Image E2E" fully) are not satisfiable without the backend work above.

---

## 3. Backend Issues Blocking GOA-058

### 3.1 🔴 `_resolve_task_context` list/dict shape mismatch — **FIXED, but no defense against it recurring**

- **Root cause (historical, now fixed):** `session_service.py`'s `_resolve_task_context` assumed `questions` JSONB was always a `{task1: {...}, task2: {...}}` dict, and called `.get()` on it. Real ingested Cambridge questions store `questions` as a **list** (`[{number, prompt, ...}, {...}]`). A non-empty list is truthy, so `questions_data or {}` never activated the `{}` fallback, and `.get()` raised `AttributeError` — uncaught, surfacing as HTTP 500 on every real writing submission.
- **Impact:** Was total — every real (non-fixture) writing task submission failed.
- **Current status:** Fixed at `session_service.py:641-708`, reusing the existing `_question_list` normaliser so this and `_public_question` can never disagree about shape again. 4 regression tests added and passing.
- **Residual risk:** None identified for this specific bug. Noted here because it is the single most severe defect this ticket's investigation uncovered, and its presence for as long as it was (undetected by the original test suite, whose fixtures used the wrong shape) is a cautionary tale for §3.6 below.

### 3.2 🔴 `highlighted_issues`/`inline_issues` field-name mismatch — **FIXED**

- **Root cause (historical, now fixed):** `writing_client.py`'s Pydantic model required `highlighted_issues: [{issue, start, end}]`, a shape the Writing service has never emitted (it sends `inline_issues: [{issue_type, start_char, end_char}]`). Validating a genuine response raised `ValidationError`, uncaught by the retry loop, surfacing as an unhandled 500.
- **Current status:** Fixed via `AliasChoices` at `writing_client.py:28-80` — accepts both spellings, canonical on the producer's names, backward compatible. 7 regression tests in `tests/test_writing_client_contract.py`.

### 3.3 🟠 No automatic retry for transient network/timeout failures at the per-agent level

- **Root cause:** `agents.py:_execute` (lines 406-439) retries **only** `ValueError`/`ValidationError` (JSON-parse and schema failures). A raw `anthropic.APITimeoutError` or `APIConnectionError` from `self.client.messages.create(...)` is **not caught by that loop** — it propagates immediately out of `_execute`, is caught broadly by `evaluation.py`'s `run_one` (which just re-raises after closing the tracing span), collected by `asyncio.gather(..., return_exceptions=True)`, and fails the entire 4-agent evaluation (`evaluation.py:223-227`, "N of 4 writing agents failed").
- **Verified live:** During this audit, a probe of 3 rounds against the real AgentRouter produced one round where a single criterion agent failed with `APITimeoutError` while the other 3 succeeded — and the *entire task submission* failed as a result, with zero automatic retry of that specific failure mode.
- **Impact:** A single slow/dropped upstream call (an external condition — see §4) currently fails the whole submission for the candidate, who must manually resubmit (losing the 3 already-successful agent calls' cost, since nothing is cached on a failed attempt — see §3.6).
- **Proposed fix:** Extend the `_AGENT_PARSE_ATTEMPTS` retry loop in `_execute` to also catch `(anthropic.APITimeoutError, anthropic.APIConnectionError)`, or add a second, coarser retry at the `evaluate_exam_task` router level that re-runs only the failed criteria (not all four) when `EvaluationFailed` is raised. The latter is more efficient but a larger change; the former is a ~5-line addition to the existing `except` clause.

### 3.4 🟠 Race condition: timer expiry can trigger a duplicate concurrent submit

- **Root cause:** `WritingExam.tsx`'s `submitTask` (lines 104-150) guards against re-submission only via `if (outcomes[taskNumber]) return "submitted";` — it does **not** check `status[taskNumber] === "submitting"`. The manual "Submit" button is protected (`disabled={submitting || ...}` in `WritingTaskPanel.tsx:135`), but the `forceSubmitSignal` effect (lines 178-192, fired when the exam clock reaches zero) calls `submitTask` directly, bypassing that button-level guard.
- **Concrete failure scenario:** Candidate clicks "Submit Task 1" with the clock at 00:00:01. The request is in flight (`status[1] === "submitting"`, `outcomes[1]` still `undefined`) when the timer's `handleTimeUp` fires 1 second later. `forceSubmitSignal` increments, the effect runs, sees `outcomes[1]` is still undefined, and calls `submitTask(1)` **again** — issuing a second, concurrent `PUT /submit` for the same task and essay text.
- **Impact:** Two simultaneous 4-agent LLM evaluations for the same submission (doubles that submission's LLM cost/load on AgentRouter); the two responses race to `setOutcomes`, so the UI ends up showing whichever response resolved last (harmless in outcome since the backend UPSERTs on `(session_id, task_number)`, but wasteful and non-deterministic about *which* evaluation's band the candidate sees).
- **Proposed fix:** Add a `status[taskNumber] === "submitting"` early-return to `submitTask`, or make it dedupe on an in-flight promise per task.

### 3.5 🟢 Gateway `WriteTimeout`/`ReadTimeout` — investigated, **ruled out** as a blocker

- **What was checked:** `services/gateway/config.go:21-22` defaults `READ_TIMEOUT=5s`, `WRITE_TIMEOUT=10s`; `docker-compose.yml`'s `gateway` service does not override either, so the running container uses these defaults. This is a *different* timeout from the `examClient` (6 min) added by the recent fix — that fix addressed the Gateway's **outbound** call to the exam service; `WriteTimeout`/`ReadTimeout` govern the Gateway's **inbound** connection to the browser, at the fasthttp/Fiber level, and were untouched by that fix.
- **Why this needed verification, not assumption:** Go's `net/http.Server.WriteTimeout` documentation states it "covers the time from the end of the request header read to the end of the response write" — i.e., it can include full handler execution time, not just the final write. Fiber/fasthttp is commonly assumed to behave the same way. If true here, every writing submission (which routinely takes 30-140s) would be cut off at ~10s regardless of the exam-service-side fix.
- **What was actually tested:** This audit registered a real user, logged in, and submitted a full Task 1 → Task 2 → result flow **through the live Gateway at `localhost:8080`** (not the exam service directly, which is how the original fix was verified). Result: `submit task 1: HTTP 200 (138.2s)`, `submit task 2: HTTP 200 (133.5s)`, `result: HTTP 200 (0.0s)`, `overall_band: 2.0` — all succeeding well past the 10s `WriteTimeout` default.
- **Conclusion:** **Not a blocker.** Documented here so nobody re-investigates it. The original fix's verification (previous session) tested the exam service directly and never exercised this hop — this audit closes that gap.

### 3.6 🟡 Failed evaluations are not cached, so every retry re-runs all 4 agents from scratch

- **Root cause:** `services/writing/app/routers/essays.py`'s `evaluate_exam_task` only calls `persist_evaluation(...)` (which populates the cache row) on the success path. On `EvaluationFailed`, `essay.status = "evaluation_failed"` is committed but the cache is never written.
- **Impact:** If a candidate's Task 1 submission fails because 1 of 4 agents timed out (§3.3), the 3 agents that *did* succeed are discarded. Resubmitting the identical essay text re-runs all 4 agents from zero — full LLM cost and full latency again, compounding the AgentRouter latency problem (§4) rather than mitigating it.
- **Proposed fix:** Either cache successful individual criterion results keyed by `(essay_hash, criterion)` so a retry only re-runs the failed criterion, or accept partial success and let the coordinator retry only the failed subset before declaring the whole task failed.

### 3.7 🟡 Word-count algorithm diverges between the Writing service and everything else

- **Root cause:** `services/writing/app/agents.py:211-213`, `calculate_word_count`, uses `len(re.findall(r'\b\w+\b', text))`. This differs from (a) the frontend's `trim().split(/\s+/).filter(Boolean).length` and (b) the exam service's own `len(essay_text.split())` (used for the actual `penalty_flag` decision in `session_service.py:567`).
- **Impact:** Currently low — this value only populates the informational `CriterionEvaluation.word_count` field, which the frontend does not display or act on (confirmed: `WritingCriterionEvaluation.word_count` is read nowhere in `components/writing/`). It is technical debt, not a live bug, but it is exactly the kind of silent divergence that produced §3.1 and §3.2 — three different word-counting implementations across three services with no shared source of truth.
- **Proposed fix:** Either delete the unused field or have the Writing service accept the already-computed word count from the exam service's request instead of recomputing it with a third algorithm.

---

## 4. AI / AgentRouter Issues

### Internal (this codebase's responsibility)

| Issue | Detail |
|---|---|
| `system` parameter unreliability was undiagnosed until this fix | AgentRouter (an OpenAI-compatible relay in front of Claude) demonstrably weakens the Anthropic `system` parameter in translation. A/B tested in this session: identical prompt+essay, 4 rounds each — instruction delivered only via `system` parsed as valid JSON 2/4 times; the same text duplicated into the user turn parsed 4/4. Fixed at `agents.py:391-404` by sending the instruction both ways. **This is now fixed, but the underlying flakiness of the relay is external — see below.** |
| No retry for timeout/connection errors at agent level | §3.3 above. |
| No test coverage for any of the above | §7.1 below — this is the single largest testing gap in the whole ticket. |
| `ANTHROPIC_TIMEOUT_SECONDS` and `WRITING_CLIENT_TIMEOUT_SECONDS`/exam-service retry budget are not provably aligned | `_AGENT_PARSE_ATTEMPTS = 3` (agents.py:30), each attempt bounded by `ANTHROPIC_TIMEOUT_SECONDS = 120`. In the theoretical worst case (every attempt hangs to the full timeout), one criterion could take up to 360s, while the exam service's own `WritingClient` timeout (`writing_client.py:113-117`) defaults to 300s. If that theoretical worst case were ever hit, the exam service would time out on its own outbound call *before* the writing service's internal retries exhausted, producing a 502 for a request that might have eventually succeeded. Not observed in this audit's live testing (worst observed single round was 363.7s of *wall clock for a 4-agent parallel gather*, not a single serial 360s chain), but the budgets are not provably consistent and should be reconciled (e.g., raise `WritingClient` timeout above `_AGENT_PARSE_ATTEMPTS × ANTHROPIC_TIMEOUT_SECONDS`, or reduce parse-attempt count). |

### External (AgentRouter/provider — not fixable in this codebase)

| Issue | Detail |
|---|---|
| Latency variance | Measured live in this session: individual 4-agent evaluation rounds ranging from ~27s to **363.7s** for what should be a comparable request. This variance is why timeouts had to be set generously (120s per call, 300s for the whole task) rather than tightly. |
| Prose-instead-of-JSON responses | Measured live: even after hardening the system prompt with explicit "your reply must begin with `{`" language, the model still occasionally (measured ~1 in 6 per criterion in this session, though this rate is itself unstable/unverifiable long-term since it depends on AgentRouter's routing and the underlying model's day-to-day behavior) returns markdown prose ("# Task Response Assessment...") instead of JSON. This is inherent to going through a relay to a model that was not directly instructed by Anthropic's own SDK conventions and cannot be fully eliminated, only mitigated (which is what the retry loop does). |
| Assistant-message prefill is silently dropped | Tested and disproved in this session's history: prefilling the assistant turn with `"{"` (Anthropic's documented technique for forcing JSON) does not work through AgentRouter — the relay returns a complete, self-contained object that, when concatenated with the prefill, produces double braces and a parse error. This is documented in code comments but worth restating here: **do not attempt to reintroduce prefill as a fix** without re-verifying against AgentRouter directly first. |

---

## 5. Image / Stimulus Issues

Direct answers to the checklist in the task prompt:

| Question | Answer | Evidence |
|---|---|---|
| Does Academic Task 1 image exist? | **No.** | `StimulusPanel.tsx` renders no `<Image>` element under any code path. |
| Do pre-signed S3 URLs work? | **N/A — none are ever generated for Writing.** | No writing-stimulus equivalent of `S3AudioDeliveryService` exists in `services/exam`. |
| Does the zoom button work? | **N/A — it does not exist.** | Confirmed absent from `StimulusPanel.tsx`; the current E2E suite explicitly asserts `stimulus-zoom-button-1` has **zero** matches. |
| Image loading failures | **N/A**, no image is ever requested. |
| Fallback behavior | **Yes, and it is correct.** `StimulusPanel.tsx` unconditionally renders prompt text; a payload carrying a legacy/unexpected image field (`stimulus_image_url`, `image_s3_key`) is silently ignored rather than rendered or crashing — verified by `test/e2e/writing-exam.spec.ts:275-287` (`"Academic Task 1 stays usable even if the payload carries an image field"`) and unit test `test/unit/writing-exam.test.ts:285-306`. |
| Caching | N/A, no image pipeline exists to cache. |

**Bottom line:** this is not a partially-working feature with rough edges — it is fully absent by deliberate team decision, with clean removal (no dead image code, no broken references) and forward-compatible structure (`StimulusPanel.tsx:23-45` documents exactly what to add back and where). See §2.2 for the effort estimate to build it.

---

## 6. UX Issues

| Issue | Detail | Severity |
|---|---|---|
| Under-minimum warning shows factually wrong text for Task 2 | §2.1. | 🔴 High — a candidate-facing factual error about how their score is calculated. |
| No time-estimate messaging during a long submit | The only feedback during a 30-140s (occasionally 300s+) evaluation is a spinning icon and the button label changing to "Evaluating..." (`WritingTaskPanel.tsx:139-140`). No "this can take up to 2 minutes" copy, no progress indicator. A candidate with no context for AI evaluation latency may assume the app has frozen. | 🟠 Medium |
| No client-side timeout/cancel on the submit request | `submitWritingTask` (`lib/exam-api.ts:232-253`) is a bare `fetch` with no `AbortController` and no timeout. If the browser tab is left open on a genuinely wedged request, there is no way for the user to cancel and retry from the UI — they must reload, which discards the in-flight submission's draft (though not necessarily the backend's eventual response, which the reload will simply never see). | 🟡 Low-Medium |
| No accessibility (`aria-live`) announcements | Zero `aria-live`/`role="alert"`/`role="status"` usage anywhere in `components/writing/` (verified by grep). A screen-reader user gets no announcement when: the word counter crosses into/out of warning state, Task 1 finishes evaluating and the tab badge appears, or a submit error occurs. Sighted users see all of these visually; screen-reader users get nothing. | 🟠 Medium |
| Minor: `onCompleted()` can fire twice on the timer-expiry path | If the exam clock expires at the exact moment both tasks happen to already be submitted (or become submitted during the force-submit sequence), both the `bothSubmitted` `useEffect` (`WritingExam.tsx:166-168`) and the explicit `onCompleted()` call at the end of the force-submit loop (`WritingExam.tsx:187`) can fire. `router.push` to the same URL twice is a harmless no-op, but it's sloppy and worth a one-line guard. | 🟢 Cosmetic |
| Collapsed result cards, timer behavior, colour coding | All correct — no issues found. | — |
| Responsive layout | Out of scope by pre-existing, cross-skill design: the exam shell blocks all skills on mobile viewports (`app/exam/shell/page.tsx:205-210`, "EXAM MODE LOCKED"). Not a GOA-058-specific gap. | — |

---

## 7. Missing Tests

### 7.1 🔴 Zero automated coverage for the AgentRouter reliability fixes — the highest-priority testing gap in this report

Every one of the following behaviors was verified **manually, against the live AgentRouter service, during interactive debugging sessions** — none of it is captured as a repeatable, CI-running regression test:

- The prompt-duplicated-into-user-turn workaround (`agents.py:391-404`) — no test asserts that `messages.create` is called with the instruction present in the user-turn content, so a future refactor could silently drop this and reintroduce the original 2/4 JSON-parse failure rate with no test failure to catch it.
- The bounded re-ask loop (`agents.py:406-439`, `_AGENT_PARSE_ATTEMPTS`) — no test exercises "first response is unparsable prose, second response is valid JSON, `_execute` returns the second one" or "all N attempts fail, raises with the last error attached."
- `sentence_examples` accepting more than 3 and trimming to 3 (`agents.py:140-146,448-452`) — no test for the surplus case, only the implicit `min_length=3` schema constraint.
- The exam-service `WritingClient` timeout/retry env-var overrides (`writing_client.py:113-126`, `WRITING_CLIENT_TIMEOUT_SECONDS`/`WRITING_CLIENT_MAX_RETRIES`) — `tests/test_writing_client_contract.py` has zero tests for these constructor defaults or their env-var overrides.
- The `WritingClient`'s 502 vs generic-failure branching under retry (what happens when `max_retries > 0` and the first attempt 502s) — untested.

**Recommendation:** add, at minimum: (a) a unit test in `services/writing/tests/unit/` that mocks `AsyncAnthropic.messages.create` to return unparsable text on attempt 1 and valid JSON on attempt 2, asserting `_execute` succeeds and used 2 attempts; (b) a unit test asserting the instruction text appears in the outgoing user-turn content, not only in `system`; (c) a unit test for `sentence_examples` trimming; (d) env-var-override tests for `WritingClient.__init__`.

### 7.2 🟠 No test for the Task 2 under-minimum warning content (would have caught §2.1)

`test/unit/writing-exam.test.ts:89-94` (`"keeps the warning copy verbatim"`) only asserts the constant's literal value — it never asserts what text is shown *for Task 2*, which is exactly the bug in §2.1. A test asserting `underMinimumWarning(2)` mentions "250 words" (once §2.1 is fixed) would be the regression guard.

### 7.3 🟠 No test for the timer-expiry double-submit race (§3.4)

No E2E or unit test simulates `forceSubmitSignal` firing while `status[taskNumber] === "submitting"`. Given this is a genuine race condition with an observable effect (duplicate network calls), it is testable: mock `submitWritingTask` with a controllable delay, trigger a manual submit, then trigger `forceSubmitSignal` before the mock resolves, and assert `submitWritingTask` was called exactly once for that task.

### 7.4 🟡 No integration/E2E test goes through the real Gateway

Every E2E test in `test/e2e/writing-exam.spec.ts` stubs the Gateway's REST responses at the network layer (`page.route(...)`) rather than hitting a real Gateway → exam service → writing service chain. This is the correct and standard pattern for fast, deterministic UI tests (matches the established `reading-exam.spec.ts` convention) — **not a defect** — but it does mean the full-stack integration (including the Gateway's own timeout config, §3.5) has **no automated coverage at all** and was only verified manually in this audit. Consider a small number of `@slow`/manual/nightly integration tests that exercise the real chain, given how much of this ticket's actual risk lived in cross-service timeout/contract mismatches rather than UI logic.

### 7.5 🟢 "Image E2E" from the ticket's test list

Explicitly not implemented, matching the deliberate scope decision in §2.2. Should be added when the stimulus-image backend work lands — the current E2E file already has a `TODO(GOA-058 follow-up)` comment (`test/e2e/writing-exam.spec.ts:258-263`) marking exactly where.

---

## 8. Technical Debt

| Item | Why it's debt, not a bug | Reference |
|---|---|---|
| Single long-lived HTTP request instead of a background job + polling pattern | The whole per-task submit is one synchronous request the browser holds open for up to several minutes. Comments in the code ("evaluation runs in the background") describe the *UI effect* (Task 2 stays usable) but the actual mechanism is not a background job — it's a foreground request that happens not to block a *different* part of the UI. A dropped connection, a restrictive corporate proxy with its own request-duration cap, or a closed browser tab mid-request loses that submission's LLM work entirely, with no way to poll for a result that might complete anyway. A true async pattern (submit → 202 Accepted → poll or WebSocket for completion) would be materially more robust, at real implementation cost. | `lib/exam-api.ts:232-253`, `WritingExam.tsx:104-150` |
| Failed evaluations aren't cached | §3.6 — every retry after any failure re-runs all 4 agents from scratch. | `services/writing/app/routers/essays.py` |
| Three divergent word-counting algorithms across the codebase | §3.7 — currently harmless (the divergent one is unused by the frontend) but a latent trap for the next person who wires that field up. | `agents.py:211-213` vs `session_service.py:567` vs `lib/writing-exam.ts:61-63` |
| No `aria-live` anywhere in the Writing components | §6. | `components/writing/*.tsx` |
| No client-side request timeout/cancel | §6. | `lib/exam-api.ts` |
| Exam-service and Writing-service timeout budgets not provably reconciled | §4 internal table, last row. | `agents.py:30` + `writing_client.py:113-117` |
| `onCompleted()` can double-fire | §6, cosmetic. | `WritingExam.tsx:166-192` |

---

## 9. Suggested Follow-up Tickets

### GOA-058-A — Fix under-minimum warning text for Task 2
- **Priority:** P1 (candidate-facing factual error)
- **Description:** Parameterize `UNDER_MINIMUM_WARNING` by task number so Task 2's warning references 250 words, not 150. Update both live-typing (`WritingTaskPanel.tsx`) and post-submission (`TaskResultCard.tsx`) call sites, plus the pinned unit test.
- **Files:** `services/frontend/lib/writing-exam.ts`, `components/writing/WritingTaskPanel.tsx`, `components/writing/TaskResultCard.tsx`, `test/unit/writing-exam.test.ts`
- **Complexity:** Small (1-2 hours)

### GOA-058-B — Regression tests for the AgentRouter reliability fixes
- **Priority:** P1 (currently the least-tested, most-recently-broken part of the system)
- **Description:** Add unit tests for the retry-on-unparsable-JSON loop, the system-prompt-duplicated-into-user-turn behavior, `sentence_examples` trimming, and the `WritingClient` timeout/retry env-var overrides. See §7.1 for the specific test list.
- **Files:** `services/writing/tests/unit/test_writing_agents.py` (new tests), `services/exam/tests/test_writing_client_contract.py` (new tests)
- **Complexity:** Medium (½–1 day)

### GOA-058-C — Fix the timer-expiry double-submit race
- **Priority:** P2
- **Description:** Guard `submitTask` against re-entry while `status[taskNumber] === "submitting"`, so a timer expiry that coincides with an in-flight manual submit cannot fire a second concurrent request for the same task.
- **Files:** `services/frontend/components/writing/WritingExam.tsx`
- **Complexity:** Small (1-2 hours, plus the regression test from §7.3)

### GOA-058-D — Retry transient LLM errors at the per-agent level
- **Priority:** P2
- **Description:** Extend `_execute`'s retry loop to also catch `anthropic.APITimeoutError`/`APIConnectionError`, not only JSON-parse failures, so a single slow AgentRouter response doesn't fail an otherwise-successful 4-agent evaluation.
- **Files:** `services/writing/app/agents.py`
- **Complexity:** Small (~half a day including tests)

### GOA-058-E — Cache partial/successful criterion results so retries aren't full-cost
- **Priority:** P3
- **Description:** Persist per-criterion results even when the overall task evaluation fails, so a resubmission of identical text can skip criteria that already succeeded.
- **Files:** `services/writing/app/routers/essays.py`, `services/writing/app/services/evaluation_store.py`
- **Complexity:** Medium (1-2 days — touches caching key design)

### GOA-058-F — Reconcile timeout budgets across the exam↔writing↔AgentRouter chain
- **Priority:** P3
- **Description:** Ensure `WritingClient`'s timeout is provably ≥ the writing service's own worst-case per-task retry budget (`_AGENT_PARSE_ATTEMPTS × ANTHROPIC_TIMEOUT_SECONDS`), so the exam service never gives up on a call the writing service might still complete.
- **Files:** `services/exam/app/services/writing_client.py`, `services/writing/app/agents.py`, `docker-compose.yml`
- **Complexity:** Small (config/constant change, but needs careful math + a comment explaining the relationship so it doesn't silently drift again)

### GOA-058-G — Accessibility pass on Writing exam components
- **Priority:** P3
- **Description:** Add `aria-live="polite"` regions for word-count state transitions, task-evaluated notifications, and submit errors.
- **Files:** `components/writing/WritingTaskPanel.tsx`, `components/writing/WritingExam.tsx`, `components/writing/TaskResultCard.tsx`
- **Complexity:** Small (½ day)

### GOA-058-H — Client-side submit timeout + user-facing duration expectation
- **Priority:** P3
- **Description:** Add an `AbortController`-based timeout to `submitWritingTask`, and surface "This usually takes 30 seconds to 2 minutes" copy near the "Evaluating..." state.
- **Files:** `services/frontend/lib/exam-api.ts`, `components/writing/WritingTaskPanel.tsx`
- **Complexity:** Small (½ day)

### GOA-058-I — Academic Task 1 stimulus image pipeline (the original AC #2)
- **Priority:** P1 for the *ticket*, but explicitly out of `Service: Frontend` scope
- **Description:** Full pipeline per §2.2: chart extraction during ingestion, S3 upload, a pre-signing service mirroring `S3AudioDeliveryService`, exposing the URL on the session API, restoring the writing service's image-required guard, and restoring the frontend `<Image>` + zoom modal (already documented step-by-step in `StimulusPanel.tsx:23-45`).
- **Files:** `services/exam/app/ingestion/writing_parser.py`, a new S3 pre-sign service, `services/exam/app/services/session_service.py`, `services/writing/app/evaluation.py`, `services/frontend/lib/normalizeWritingTasks.ts`, `services/frontend/components/writing/StimulusPanel.tsx`, `services/frontend/test/e2e/writing-exam.spec.ts`
- **Complexity:** Large (multi-sprint, cross-service)

### GOA-058-J — Consolidate word-counting to one implementation
- **Priority:** P4 (debt, not urgent — currently harmless)
- **Description:** Delete the unused, divergent `calculate_word_count` in the Writing service, or have it accept the exam service's already-computed count instead of recomputing with a third algorithm.
- **Files:** `services/writing/app/agents.py`
- **Complexity:** Small (~1 hour)

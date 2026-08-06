# GOA — Information Architecture Redesign Proposal

**Status:** Proposal for review. No code written.
**Scope:** Navigation, route structure, Practice/History surfaces, onboarding, CV Review placement.
**Grounded in:** a full read of `services/frontend/app`, `services/frontend/components`, `services/gateway/server.go`, `services/exam`, `services/writing`, `services/speaking`.

---

## 1. Executive Summary

Three findings drive this document.

**First, your instinct on Practice is right, but the tree you proposed reproduces the problem it solves.** Practice today is not a place — it is a mode of the Chat page. That is genuinely wrong and should change. But a top-level `Practice` section sitting beside `IELTS Exam` splits the same four skills across two homes, each with its own history. A user asking "how is my Writing?" would then have two places to look instead of one. I recommend organising by **skill** (the object) rather than by **mode** (Practice vs Exam), which is what Linear and Notion actually do, and which costs no more to build.

**Second, your instinct on CV upload in onboarding is right, and the code agrees more strongly than you may realise.** The CV step is already paywalled server-side (`POST /api/writing/cv/upload` carries `RequirePaid` at [server.go:181](../services/gateway/server.go#L181)), so every free user who reaches step 4 today hits a 402 and an upgrade panel. Worse, the wizard's own handler signature is `handleFinish(_cv: …)` — [onboarding/page.tsx:131](../services/frontend/app/onboarding/page.tsx#L131) — the underscore is real: **the CV result is never used.** The step is already architecturally orphaned. Removing it has **zero backend implications**.

**Third, the History story is far better supported by the backend than the UI suggests, and there are three broken calls in production code.** Writing evaluations are already persisted (`Essay.evaluation_result`, written by [evaluation_store.py:53](../services/writing/app/services/evaluation_store.py#L53)); exam history and weak-areas endpoints are already implemented in the exam service. Neither is reachable from the browser. Meanwhile `/api/profile/update-scores`, called twice from the exam results page, **does not exist anywhere** — not in the gateway, not as a Next route handler.

Recommended shape:

```
Dashboard · Chat · IELTS · Opportunities · Checklists · CV Review · Profile
```

with IELTS organised skill-first, and each skill owning its own Practice, Exam, and History.

---

## 2. Current Architecture

### 2.1 Route tree (verified — `find app -name page.tsx`)

```
app/
├── page.tsx                              /                      marketing
├── onboarding/page.tsx                   /onboarding            4-step wizard (outside app shell)
├── design-system/page.tsx                /design-system
├── (auth)/
│   ├── login · register · forgot-password · reset-password · verify-email/[token]
├── (app)/                                ← authenticated shell, has Sidebar
│   ├── chat/page.tsx                     /chat
│   ├── opportunities/page.tsx            /opportunities
│   ├── checklists/page.tsx               /checklists
│   ├── checklist/[programId]/page.tsx    /checklist/:id         (note: singular, legacy path)
│   ├── exam/page.tsx                     /exam
│   ├── exam/shell/page.tsx               /exam/shell
│   ├── exam/results/page.tsx             /exam/results
│   ├── speaking/page.tsx                 /speaking
│   ├── speaking/history/page.tsx         /speaking/history
│   ├── speaking/history/[id]/page.tsx    /speaking/history/:id
│   └── profile/page.tsx                  /profile
└── speaking/share/[token]/page.tsx       /speaking/share/:token  (public, outside shell)
```

**There is no `/dashboard`. There is no `/practice`. There is no `/cv-review`.** No Next.js route handlers exist at all (`find app -name route.ts` → empty).

### 2.2 Sidebar (`components/ui/sidebar.tsx:73–104`)

| # | Label | href | Notes |
|---|---|---|---|
| 1 | Chat | `/chat` | |
| 2 | Opportunities | `/opportunities` | |
| 3 | Checklists | `/checklists` | `alsoActiveFor: ["/checklist/"]` |
| 4 | IELTS | `/exam` | prefix match |
| 5 | Speaking | `/speaking` | prefix, child: History → `/speaking/history` |
| 6 | CV Review | **`null`** | inert, `"Requires GOA Pro — coming soon"` + "Soon" badge |
| 7 | Profile | `/profile` | |

Seven items, one of which is a dead control. The sidebar already supports one level of children — the mechanism you want for Practice exists and is proven by the Speaking → History pair.

### 2.3 Where Practice actually lives

Neither Writing nor Speaking Practice has a page. Both are **modes of `ChatShell`**:

- `type ChatMode = "chat" | "writing"` — [chat-shell.tsx:104](../services/frontend/components/chat/chat-shell.tsx#L104)
- `activePractice: "speaking" | "writing" | null` — [chat-input.tsx:17](../services/frontend/components/chat/chat-input.tsx#L17)
- Two buttons in the composer, mutually exclusive: `writingLocked = activePractice === "speaking"`, `speakingLocked = activePractice === "writing"` ([chat-input.tsx:69–70](../services/frontend/components/chat/chat-input.tsx#L69))

`/speaking` exists as a landing page but **cannot start a session** — its primary button is `<Link href="/chat">Open Chat</Link>` ([speaking/page.tsx:70](../services/frontend/app/(app)/speaking/page.tsx#L70)), with the copy "Sessions run in Chat, where the microphone and live transcript live." Writing has no equivalent landing page at all.

### 2.4 Gateway API surface (verified — `services/gateway/server.go:131–305`)

```
Public:    POST /users · POST /auth/{login,refresh,forgot-password,reset-password}
           GET  /auth/verify-email/:token · POST /auth/logout
           GET  /speaking/sessions/public/:token          ← unauthenticated share
Admin:     /api/admin/* · /admin/costs

/api  (JWT + 60 req/min + ResolveSubscription):
  POST   /chat                                    free   AIRateLimiter "chat"
  GET    /chat/sessions/:sessionId/history        free
  DELETE /sessions/memory                         free
  POST   /writing/essays/upload                   PAID   + 5000-char validator
  POST   /writing/essays/:essayId/evaluate        PAID   AIRateLimiter "essay_evaluation"
  POST   /writing/cv/upload                       PAID
  POST   /writing/cv/review                       PAID   AIRateLimiter "cv_review"
  /api/exam/*  (group-level RequirePaid):
    POST  /sessions                               + ExamStartRateLimiter (3/hr, shared)
    GET   /listening/start                        + ExamStartRateLimiter
    PUT   /sessions/:id/submit                    + ownership
    GET   /sessions/:id/result                    + ownership
    PUT   /reading/:id/submit · PUT /listening/:id/submit   + ownership
    GET   /sessions/:id · PATCH /sessions/:id/heartbeat
    GET   /progress
  GET    /speaking/sessions                       free
  GET    /speaking/sessions/:id                   free
  POST   /speaking/sessions/:id/share             free
  GET    /speaking/ws                             free   ← WebSocket upgrade
  POST   /opportunities/query                     free   AIRateLimiter
  GET    /checklists/:programId  · PUT /checklists/:programId/items/:itemId
  GET    /checklists/:programId/financial
  GET    /profile · PUT /profile
  GET    /notifications
Also:  POST /cv/upload                            PAID   ← duplicate of /api/writing/cv/upload
```

### 2.5 Storage

| Table | Service | Key fields | Practice/Exam |
|---|---|---|---|
| `speaking_sessions` | speaking (Go) | `question_prompt`, `question_type`, `transcript`, `evaluation` JSONB, `overall_band` (nullable), `created_at`, share token | Practice only |
| `essays` | writing (Py) | `extracted_text`, `submission_type`, `exam_session_id`, `exam_type`, `task_number`, `evaluation_cache_key`, `evaluation_result` JSONB | **Both** — discriminated by `submission_type` |
| `cv_reviews` | writing (Py) | `s3_key`, `status`, `content_hash`, `extracted_text`, `structured_data` JSONB, `processed_at` | — |
| `exam_sessions` | exam (Py) | `exam_type`, `skill_area`, `status`, `started_at`, `submitted_at`, `time_limit_seconds` | Exam only |
| `exam_results` | exam (Py) | `raw_score`, `band_score`, `section_scores` JSONB, `agent_responses`, `graded_at` | Exam only |

---

## 3. Problems Identified

### P1 — Practice is a mode, not a place
No route, no page, no bookmark, no link you can send someone. Both practice modes are reachable only by opening Chat and finding the right button. This is the root problem and your diagnosis is correct.

### P2 — `/speaking` is a landing page that cannot land anything
It shows stats and links to Chat. It is a signpost pointing at a different page. Duplicating this pattern for Writing (as `Practice > Writing Practice` would) doubles the indirection rather than removing it.

### P3 — Writing Practice has no history, though the data exists
`persist_evaluation()` writes `{evaluations, overall_band}` into `Essay.evaluation_result` on every completed evaluation ([evaluation_store.py:53–61](../services/writing/app/services/evaluation_store.py#L53)). Every practice essay a user has ever submitted is already in the database with its band. There is no API to list them and no page to show them.

### P4 — Exam history and weak-areas are implemented but unreachable
`services/exam/app/api/history.py` implements `GET /users/{id}/exam-history`, `GET /users/{id}/progress`, `GET /users/{id}/weak-areas`, with a `RecommendationProfile` schema carrying `reading_band`, `listening_band`, `speaking_band`, `writing_band`, `weak_areas`, `exam_count`. **Only `/progress` has a gateway route.** The other two are finished backend work with no way to reach them.

### P5 — Three broken or dead client calls

| Call | Location | Problem |
|---|---|---|
| `POST /api/profile/update-scores` | [exam/results/page.tsx:106](../services/frontend/app/(app)/exam/results/page.tsx#L106) and `:143` | **No such endpoint.** Not in `server.go`; no `route.ts` exists anywhere in `app/`. It 404s. Masked because `test/e2e/writing-exam.spec.ts:243` mocks it. |
| `POST /api/writing/evaluate` | `lib/writing-api.ts:43` | No such gateway route (`/writing/essays/:id/evaluate` is the real one). Also **`evaluateEssay` is never called** — only its types are imported. Dead code. |
| `POST /cv/upload` | [server.go:298](../services/gateway/server.go#L298) | Duplicate of `/api/writing/cv/upload` with the same handler and a hand-rolled middleware chain. |

### P6 — Onboarding step 4 is orphaned and paywalled
`CvUploadStep` calls `authApi.uploadCv` → `POST /api/writing/cv/upload`, which is `RequirePaid`. Free users get `upgrade-required` and a panel explaining they can skip. Meanwhile the wizard's finish handler takes the CV result as `_cv` and **discards it** — `buildProfilePayload()` only reads `academic`, `language`, `targets`. The step cannot affect the outcome of the wizard under any circumstances.

### P7 — Sidebar mixes two unrelated jobs at one altitude
Chat, Opportunities, Checklists, IELTS, Speaking, CV Review, Profile. Two of those (IELTS, Speaking) are exam prep; three (Opportunities, Checklists, CV Review) are applying for places. They are interleaved with no visual grouping, and one skill (Speaking) is promoted to sit beside the section that contains the other three.

### P8 — `Essay` has no band column
`overall_band` lives inside the `evaluation_result` JSONB. A Writing trend chart would need either a JSONB extraction on every query or a generated/materialised column. Worth deciding before building the chart, not after.

### P9 — Evaluation cache is not user-scoped
`find_cached_evaluation()` ([evaluation_store.py:33](../services/writing/app/services/evaluation_store.py#L33)) matches on `evaluation_cache_key` alone with no `user_id` filter. Two users submitting identical text share a row's evaluation. Harmless for correctness, but it means a Writing History built naively on `evaluation_cache_key` could surface another user's essay. Flagging now because History is exactly the feature that would expose it.

---

## 4. Proposed Information Architecture

### 4.1 The core decision: organise by skill, not by mode

Your proposal:

```
IELTS Exam ──┬── Reading   Listening   Writing   Speaking
Practice   ──┴── Speaking Practice → History
                 Writing Practice  → History
```

The problem: **Practice and Exam are modes of the same four objects.** Splitting them at the top level means Writing appears in two sections, each with its own history and its own progress. The question a user actually asks is not "show me my practice" — it is "how is my Writing?" Under your tree that question has two answers in two places.

Recommended instead:

```
IELTS ──┬── Reading    → Practice · Exam · History
        ├── Listening  → Practice · Exam · History
        ├── Writing    → Practice · Exam · History
        └── Speaking   → Practice · Exam · History
```

Why this is better, concretely:

1. **One answer per question.** "How is my Writing?" → `/ielts/writing`. Practice attempts, exam attempts, and the trend live on one page.
2. **It costs no more to build.** Your tree needs `/practice`, `/practice/speaking`, `/practice/speaking/history`, `/practice/writing`, `/practice/writing/history` — five new routes, plus keeping `/exam/*`. Mine needs `/ielts`, and four skill pages — five routes — and the history component is written **once** and reused four times instead of twice.
3. **It absorbs the existing anomaly.** `/speaking` and `/speaking/history` already are a skill page with a history sub-view. The proposal generalises what is already the best-structured corner of the app rather than adding a parallel structure beside it.
4. **It makes the gaps legible instead of hiding them.** Reading and Listening have no Practice; Speaking has no Exam. In a skill-first IA those are visibly empty tabs with honest copy. In a mode-first IA, `Practice` silently contains only two of four skills and looks complete.

The honest cost: **two of eight cells are empty at launch** (Reading Practice, Listening Practice — plus Speaking Exam, and Listening Exam is disabled entirely). A skill-first IA displays that. I consider that a feature — the current product hides it behind a Practice section that simply omits the missing skills — but you should make that call deliberately.

**If you prefer less refactor**, the middle path is: keep `/exam/*` where it is, and build `/practice` exactly as you described. It is a genuine improvement over today. It just leaves the two-homes-per-skill problem for later, and later is more expensive.

### 4.2 The second decision: Career grouping

You asked whether CV Review should be top-level or nested under "Career Tools". Neither, quite. The cleanest option is **labelled non-interactive section headers**, which is the Linear pattern:

```
  Dashboard
  Chat

  PREPARE
    IELTS

  APPLY
    Opportunities
    Checklists
    CV Review

  Profile
```

Headers are cheap, add no click depth, and give the sidebar structure without a collapsible tree. A collapsible "Career Tools" group adds a click to reach three of your six destinations — over-nesting for a product this size.

### 4.3 Old vs new — side by side

Three columns: what exists today, what you proposed, and what this document recommends.

| | **Current** | **Proposed (yours)** | **Recommended (skill-first)** |
|---|---|---|---|
| **Shape** | Practice = a mode of `/chat`; Speaking promoted to top level; CV Review inert | `Practice` and `IELTS Exam` as sibling top-level sections | One `IELTS` section, four skills, each with Practice/Exam/History tabs |
| **Sidebar items** | 7 (one dead) | 5 + nested practice tree | 7 + 2 non-interactive headers |
| **"How is my Writing?"** | No answer — no writing history exists | Two answers: `/practice/writing` and `/exam` | One answer: `/ielts/writing` |
| **New routes** | — | ~5 (`/practice/*`) + keep `/exam/*` + `/dashboard` + `/cv-review` | ~5 (`/ielts/*`, incl. one `[skill]` param route) + `/dashboard` + `/cv-review` |
| **History components** | Written once, used once (Speaking) | Written once, used 2× (Speaking, Writing) | Written once, used 4× |
| **Pros** | Nothing to build | Big improvement over today; smaller conceptual leap; leaves `/exam` untouched, so lower blast radius | Single home per skill; generalises the app's best-structured corner; gaps become visible; cheapest per-skill marginal cost |
| **Cons** | Practice unlinkable, unbookmarkable, undiscoverable; `/speaking` is a signpost to another page | Splits each skill across two sections, each accruing its own history and progress; Reading/Listening silently absent from Practice | Two of eight tabs ship empty (Reading/Listening Practice); `[skill]` route needs param validation; bigger move of `/exam/*` |
| **Risks** | Compounding — every new practice mode makes `ChatShell` heavier | Same `ChatShell` extraction risk (R1); plus the two-homes problem gets more expensive to undo later | Same `ChatShell` extraction risk (R1); more redirects (R7); more e2e churn (R2) |
| **Complexity** | Low now, rising | Medium — parallel structure beside the existing one | Medium — one structure, more of it moved at once |
| **Maintainability** | Poor — practice state lives in a 1000-line chat component | Fair — two places to change when a skill gains a feature | Good — one place per skill; adding Reading Practice is filling a tab, not adding a section |
| **User experience** | Practice is hidden; no writing history at all | Practice becomes findable; history split by mode, which is not how users think | Practice findable; history organised the way users ask the question |

The decisive line is **"How is my Writing?"**. Both proposals fix discoverability. Only the skill-first one gives that question a single answer, and it does so without costing more routes or more work.

---

## 5. Navigation Tree

```
Dashboard                    /dashboard              NEW
Chat                         /chat                   unchanged
─ PREPARE ─────────────────────────────────────────────────
IELTS                        /ielts                  overview: 4 skill cards, overall band, weak areas
  Reading                    /ielts/reading          tabs: Practice │ Exam │ History
  Listening                  /ielts/listening        tabs: Practice │ Exam │ History
  Writing                    /ielts/writing          tabs: Practice │ Exam │ History
  Speaking                   /ielts/speaking         tabs: Practice │ Exam │ History
─ APPLY ───────────────────────────────────────────────────
Opportunities                /opportunities          unchanged
Checklists                   /checklists             unchanged
CV Review                    /cv-review              NEW (replaces the inert "Soon" item)
───────────────────────────────────────────────────────────
Profile                      /profile                unchanged
```

Sidebar children (the existing `NavItem.children` mechanism) reveal the four skills only while the IELTS section is active — the behaviour `sidebar.tsx:249` already implements for Speaking → History.

---

## 6. Route Tree

```
(app)/
├── dashboard/page.tsx                    NEW
├── chat/page.tsx                         unchanged
├── ielts/
│   ├── page.tsx                          NEW  (replaces /exam)
│   ├── [skill]/page.tsx                  NEW  (tabbed: practice | exam | history)
│   │      ?tab=practice|exam|history — tab in the query string, so a tab is linkable
│   ├── [skill]/session/[id]/page.tsx     NEW  (history detail — replaces /speaking/history/:id)
│   ├── exam/shell/page.tsx               MOVED from /exam/shell
│   └── exam/results/page.tsx             MOVED from /exam/results
├── cv-review/page.tsx                    NEW
├── opportunities/page.tsx                unchanged
├── checklists/page.tsx                   unchanged
├── checklist/[programId]/page.tsx        unchanged  (legacy path, keep — e2e-covered)
└── profile/page.tsx                      unchanged
```

**Redirects required** (Next `redirect()` in a page, or `middleware.ts`):

| Old | New | Why |
|---|---|---|
| `/exam` | `/ielts` | |
| `/exam/shell?…` | `/ielts/exam/shell?…` | preserve query string — session id lives there |
| `/exam/results?…` | `/ielts/exam/results?…` | preserve query string |
| `/speaking` | `/ielts/speaking` | |
| `/speaking/history` | `/ielts/speaking?tab=history` | |
| `/speaking/history/:id` | `/ielts/speaking/session/:id` | |
| `/speaking/share/:token` | **unchanged** | public, unauthenticated, may be in the wild — must not move |

`/speaking/share/[token]` sits outside `(app)` deliberately and must stay exactly where it is; shared links have been minted against that path.

**On the `[skill]` dynamic segment:** four hardcoded folders (`reading/`, `writing/`, …) would be more explicit, but a single `[skill]` route with `generateStaticParams` keeps the tab shell, the history list, and the trend chart written once. Given the four skills differ only in which Practice/Exam runtime they mount, one parameterised route is the better trade. Validate the param against a whitelist and `notFound()` otherwise.

---

## 7. Sidebar Structure

Changes to `NAV_ITEMS` in [sidebar.tsx:73](../services/frontend/components/ui/sidebar.tsx#L73):

```
REMOVE   { label: "Speaking", href: "/speaking", children: [History] }
           → absorbed into IELTS as one of four skills

CHANGE   { label: "IELTS", href: "/exam" }
           → { label: "IELTS", href: "/ielts", children: [Reading, Listening, Writing, Speaking] }

CHANGE   { label: "CV Review", href: null, unavailableReason: "Requires GOA Pro — coming soon" }
           → { label: "CV Review", href: "/cv-review" }
           the one dead control in the sidebar becomes real

ADD      { label: "Dashboard", href: "/dashboard" }  at position 1

ADD      section headers: "PREPARE" before IELTS, "APPLY" before Opportunities
           requires a new `type: "section"` variant in the NavItem union
```

Net: 7 items → 7 items + 2 headers, but with one dead entry removed, one new destination added, and a coherent grouping. The `href: null` / "Soon" badge rendering path (`sidebar.tsx:199–216`) is retained — it will still be needed for Reading Practice and Listening Practice tabs, but at tab level rather than sidebar level.

---

## 8. Screen-by-Screen Changes

### 8.1 `/dashboard` — NEW
The one screen that answers "where do I stand and what next." Sources: `GET /api/exam/progress` (exists), plus the two endpoints that need gateway routes (§10). Contents: overall band, four skill tiles with latest band and trend arrow, weak-areas list, recent activity (last 5 sessions across all skills), next-action card. **Onboarding should redirect here instead of `/opportunities`** ([onboarding/page.tsx:148](../services/frontend/app/onboarding/page.tsx#L148)).

### 8.2 `/ielts` — replaces `/exam`
Today's `exam/page.tsx` already computes `overallBand` and `weakestSkill` client-side and renders four skill cards with `latestBand`. The redesign keeps that logic and changes what a card links to: `/ielts/{skill}` instead of directly creating a session. Session creation moves down to the skill page's Exam tab, which is where the "3 sessions/hour" limit and the paid gate belong contextually.

### 8.3 `/ielts/[skill]` — NEW, the centrepiece
Header: skill name, current band, attempt count. Three tabs:

| Tab | Reading | Listening | Writing | Speaking |
|---|---|---|---|---|
| **Practice** | empty state, "not yet available" | empty state | `EssayComposer` + `WritingEvaluationPanel`, lifted out of `ChatShell` | `SpeakingSessionPanel` + mic, lifted out of `ChatShell` |
| **Exam** | `ReadingExam` launcher | disabled — audio gap | `WritingExam` launcher | empty state |
| **History** | exam attempts | — | practice + exam essays | practice sessions + `BandTrendChart` |

The Practice tab is where the real work is: `EssayComposer`, `WritingEvaluationPanel`, `SpeakingSessionPanel`, `MicButton`, and `WaveformCanvas` all currently receive their state from `ChatShell`. They must be extracted into self-contained practice containers that own their own state. This is the largest single item in the plan.

### 8.4 `/ielts/[skill]/session/[id]` — history detail
Generalises `speaking/history/[id]/page.tsx`. For Speaking: transcript, `EvaluationBreakdown`, `ShareButton` (all exist). For Writing: essay text, per-criterion feedback, `EssayHighlighter` (exists). For Reading/Writing exam attempts: the existing results components.

### 8.5 `/chat` — reduced, not removed
Chat keeps the ability to *launch* practice, but hands off instead of hosting. The two composer buttons become links to `/ielts/writing?tab=practice` and `/ielts/speaking?tab=practice`. The mutual-exclusion lock logic (`writingLocked` / `speakingLocked`) disappears with them — that state exists only because both modes shared one page.

This is a real simplification: `chat-shell.tsx` currently carries `chatMode`, `writingLoading`, `writingError`, `writingEvaluations`, `writingOverallBand`, `submittedEssay`, `improvedEssay`, `speakingOpen`, and `activePractice`. All of it leaves.

**Counter-consideration worth your judgement:** the orchestration service classifies chat intent and can route a user into writing/speaking practice conversationally. If a user types "check my essay" in Chat, do we still evaluate inline, or navigate them away mid-conversation? My recommendation: evaluate inline for that turn (keeping the existing `writing_url` SSE path), then show a "saved to your Writing history" link. Navigation mid-conversation is hostile; losing the result is worse.

### 8.6 `/onboarding` — 4 steps → 3
Remove `CvUploadStep` entirely. Step 3 (Targets) becomes the finisher. Specific edits:
- `ONBOARDING_STEPS` in `components/onboarding/onboarding-stepper.tsx` — drop the 4th entry; `TOTAL_STEPS` derives from it automatically ([onboarding/page.tsx:29](../services/frontend/app/onboarding/page.tsx#L29))
- The `furthestAnswered` clamp ([page.tsx:109–116](../services/frontend/app/onboarding/page.tsx#L109)) currently returns `4` when destinations are set — becomes `3`
- `handleFinish(_cv)` loses its parameter; `TargetsStep`'s `onNext` becomes `onComplete`
- Redirect target `/opportunities` → `/dashboard`
- Delete `components/onboarding/CvUploadStep.tsx`
- `EMPTY_DRAFT` / draft types in `components/onboarding/types.ts` — no CV field exists to remove, confirming the step was already detached
- Update e2e specs that walk the wizard

Where the CV ask goes instead: a dismissible card on `/dashboard` and an entry on `/profile`, both linking to `/cv-review`. Asked once the user has seen value, not before.

### 8.7 `/cv-review` — NEW
Replaces the inert sidebar item. Contents: current CV card (filename, uploaded date, status), upload/replace dropzone, "Start review" action, review output, and review history if we add the listing endpoint. `cv_reviews` already carries `status`, `content_hash`, `structured_data`, and `processed_at` — the processing/complete/error states the UI needs are all representable today.

**Free-plan behaviour — recommendation: allow upload, block the review.** Reasoning: extraction is cheap (S3 + text parse), an uploaded CV creates investment, and the paywall then lands at the moment of concrete value where you can show a partial or blurred result and make a specific case. Blocking upload gives a free user an empty room and a price tag. The cost: `POST /api/writing/cv/upload` must drop `RequirePaid` (§10) and gain an upload rate limit so free accounts cannot be used as object storage. `POST /writing/cv/review` keeps `RequirePaid` unchanged.

---

## 9. Backend Impact

**No database migrations are strictly required to ship the navigation redesign.** Everything below is additive and can be sequenced independently.

| Area | Change | Required for |
|---|---|---|
| Gateway | Add 2 proxy routes for existing exam endpoints | Dashboard, exam history |
| Gateway | Add 1 writing history route + 1 writing service endpoint | Writing History |
| Gateway | Move `RequirePaid` from cv/upload to cv/review only | Free-tier CV upload |
| Gateway | Delete duplicate `POST /cv/upload` | Cleanup (P5) |
| Frontend | Remove `/api/profile/update-scores` calls, or build the endpoint | Fixing P5 |
| Frontend | Delete `evaluateEssay` from `lib/writing-api.ts` | Cleanup (P5) |
| Writing svc | New `GET /users/{id}/essays` (paged, user-scoped, band extracted) | Writing History |
| Writing svc | Scope `find_cached_evaluation` by `user_id` | P9 |
| Writing svc | Persist `improved_essay` | "previous rewrites" |
| Exam svc | None — history/progress/weak-areas already implemented | — |
| Speaking svc | None — list/detail/share already implemented | — |

### 9.1 Answering your §4 question directly: does the backend support Practice history?

**Speaking — yes, fully.** `GET /api/speaking/sessions` (list), `GET /api/speaking/sessions/:id` (detail), `POST …/share`. `speaking_sessions` stores transcript, evaluation JSONB, `overall_band`, `created_at`. Trend chart already built (`components/speaking/band-trend-chart.tsx`). **Nothing missing.**

**Writing — data yes, API no.** Every practice essay and its band are already persisted. What is missing:
1. A user-facing list endpoint. `GET /internal/users/{userId}/essays` exists ([internal.py:53](../services/writing/app/routers/internal.py#L53)) but is a GDPR-export shape — unpaged, internal-key auth, returns everything. Needs a proper paged sibling.
2. A gateway route for it.
3. Band is inside JSONB (P8) — decide on a generated column or an extraction index before the trend chart.
4. **Rewrites are not stored.** `improved_essay` arrives in the SSE `complete` event ([writing-stream.ts:23](../services/frontend/lib/writing-stream.ts#L23)) but `persist_evaluation()` writes only `{evaluations, overall_band}`. "Previous rewrites" needs a schema addition.

**"Continue previous sessions" — not supported for either.** `speaking_sessions` has no status/partial-state column; a session is written once, complete. `essays.status` is `pending`/`evaluated` with no draft concept. Resumable practice is a genuine new feature, not a UI change — I would drop it from the first release and let History + "practise this prompt again" cover the need.

---

## 10. API Impact

### New gateway routes (proxy only — upstream already exists)

```go
exam.Get("/history",     examHandler.GetHistory)     // → exam svc GET /users/{id}/exam-history
exam.Get("/weak-areas",  examHandler.GetWeakAreas)   // → exam svc GET /users/{id}/weak-areas
```
Both follow the exact shape of the existing `exam.Get("/progress", examHandler.GetProgress)` at [server.go:239](../services/gateway/server.go#L239) — no ownership middleware (no session id; upstream scopes by `X-User-Id`).

**Note the tier consequence:** the `/api/exam` group carries `RequirePaid` at group level ([server.go:215](../services/gateway/server.go#L215)). Registering history there makes *viewing your own past results* a paid feature. That is probably wrong — a free user who upgraded, took exams, then lapsed would lose access to their own history. Recommend registering these two outside the group, or splitting the group so reads are free and session-creation is paid.

### New writing route + endpoint

```go
api.Get("/writing/essays", writingHandler.ListEssays)   // paged, user from JWT
```
Upstream (new, in `services/writing/app/routers/essays.py`):
```
GET /essays?user_id=&limit=&cursor=&submission_type=
→ [{ id, submitted_at, submission_type, exam_type, task_number,
     overall_band, excerpt }]
```
Returns a summary shape, not full essay text — detail comes from a per-essay fetch.

### Changed routes

```go
// was: api.Post("/writing/cv/upload", subscriptionMiddleware.RequirePaid, writingHandler.UploadCV)
api.Post("/writing/cv/upload",
    middleware.AIRateLimiter(redisClient, "cv_upload", cfg.CVUploadsPerHour, time.Hour, logger, metrics),
    writingHandler.UploadCV)                              // free tier, rate-limited

// unchanged — the paywall moves here, where the AI spend is
api.Post("/writing/cv/review", subscriptionMiddleware.RequirePaid, …)
```

### Deleted

- `app.Post("/cv/upload", …)` — [server.go:298–305](../services/gateway/server.go#L298), duplicate handler
- `evaluateEssay()` in `lib/writing-api.ts` — dead, and points at a route that does not exist

### Unresolved: `/api/profile/update-scores`

Called twice from `exam/results/page.tsx` (lines 106, 143) after an exam completes, apparently to push the band into the profile so `/exam` can show it. **The endpoint does not exist.** Two options:

- **(a) Delete the calls.** `GET /api/exam/progress` already sources per-skill bands from `exam_results`, which is the authoritative record. The profile copy is redundant. — *Recommended.*
- **(b) Build it.** Only if something outside the exam service needs the band on the user profile — RAG's programme matching reads `ieltsScore` from the profile for its `min_ielts` hard gate, so there may be a real requirement here to confirm with whoever owns matching.

This needs a decision before the results page is touched. It is also worth asking why the e2e suite mocks a non-existent endpoint (`writing-exam.spec.ts:243`) — that mock is what has kept the 404 invisible.

---

## 11. Database Impact

**Required for the navigation redesign: none.**

Optional, per feature:

| # | Change | Enables | Cost |
|---|---|---|---|
| D1 | `essays.overall_band NUMERIC(2,1)` generated/backfilled from `evaluation_result->>'overall_band'` | Writing trend chart, sortable history | Migration + backfill; low risk, nullable |
| D2 | `essays.improved_essay TEXT` + write it in `persist_evaluation()` | "Previous rewrites" (your §4 ask) | Small; data only exists going forward |
| D3 | Index `essays (user_id, uploaded_at DESC)` | History list performance | Trivial |
| D4 | `user_id` filter in `find_cached_evaluation` | P9 correctness | Query change, no migration. Reduces cache hit rate — acceptable |
| D5 | `speaking_sessions.status` + partial-state columns | Resumable sessions | Non-trivial; recommend deferring |
| D6 | `cv_reviews` — nothing needed | CV Review page | Already has status/timestamps/structured output |

D1 and D3 should land together with the Writing History endpoint. D2 is independent. D5 I would not do in this cycle.

---

## 12. UX Improvements

### 12.1 Flow changes

| Flow | Today | Proposed |
|---|---|---|
| Start Writing Practice | `/chat` → find composer button → toggle mode | `/ielts/writing` → Practice tab. Linkable, bookmarkable. |
| Start Speaking Practice | `/speaking` → "Open Chat" → `/chat` → mic button | `/ielts/speaking` → Practice tab. One hop removed. |
| Review past Writing | impossible | `/ielts/writing?tab=history` |
| Review past Speaking | `/speaking` → `/speaking/history` → item | `/ielts/speaking?tab=history` → item |
| "How am I doing?" | `/exam` for 4 bands, `/speaking` for speaking | `/dashboard` |
| Upload CV | onboarding step 4 (fails on free tier) | `/cv-review`, prompted from Dashboard/Profile after signup |
| Finish onboarding | 4 steps → `/opportunities` | 3 steps → `/dashboard` |

### 12.2 Upgrade flow

Today the paywall fires in three visually different places: `useUpgradePrompt` dialog (chat), the inline `upgrade-required` Alert (onboarding CV step), and the `/exam` page's pre-emptive `upgrade.show("exam")`. Consolidate on one pattern: **a locked state on the surface itself, with the value visible behind it.** The Exam tab of a skill page shows what an exam gives you and a locked CTA; the CV Review page lets you upload and shows a redacted review preview. Pre-emptive dialogs before the user has seen anything convert worst.

`PaidFeatureId` in `lib/subscription.ts` already enumerates `exam`, `exam-reading`, `exam-writing`, `exam-listening`, `exam-speaking`, `cv-review`, `essay-evaluation`, `speaking-practice`, `writing-practice` — the granularity for per-tab gating exists.

### 12.3 States to specify per new screen

- **Empty:** no attempts yet (per skill, per tab); no CV uploaded; Dashboard with zero activity. The `EmptyState` primitive exists and `/speaking` already uses it well — reuse that copy voice.
- **Unavailable:** Reading/Listening Practice, Speaking Exam, Listening Exam. Must say *why* and, where known, what it is blocked on — the sidebar's `unavailableReason` pattern applied at tab level. Listening Exam's blocker is documented at [server.go:241–249](../services/gateway/server.go#L241) (no presigned-URL endpoint); say something honest rather than a bare "Soon".
- **Loading:** history lists and Dashboard need skeletons matching final layout — `/speaking` already does this correctly.
- **Error:** one `Alert` + retry, as `/speaking` does. Do not add a fourth error-banner style.
- **Rate-limited:** the 3-exams-per-hour limit currently surfaces as a generic failure. It deserves specific copy with the reset time.
- **Success:** post-exam and post-evaluation should both end with "saved to your history" and a link — the thing that makes History discoverable at all.

---

## 13. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Extracting practice from `ChatShell` breaks chat | **High** | The writing SSE path, the speaking WebSocket, and `activePractice` locking are entangled in one 1000+ line component. Extract to containers first with Chat still mounting them, verify, then re-mount on the new routes. Two steps, not one. |
| R2 | E2E suite breaks broadly | **High** | Specs use `getByText` 23× and assert on routes. `test/e2e/writing-exam.spec.ts` mocks a phantom endpoint. Every route move needs its spec updated in the same commit. |
| R3 | Public share links break | **High** | `/speaking/share/[token]` must not move. Explicitly out of scope for all redirects. |
| R4 | Exam history behind `RequirePaid` locks users out of their own past results | Medium | §10 — register the two read routes outside the paid group. |
| R5 | Free-tier CV upload becomes free object storage | Medium | Rate limit + size cap (the 10 MB client check already exists in `CvUploadStep`; enforce server-side too). |
| R6 | Cross-user cache leak surfaced by Writing History | Medium | Fix D4 *before* shipping the history list, not after. |
| R7 | Users bookmarked `/exam` or `/speaking/history` | Low | Redirects in §6, kept for at least one release. |
| R8 | `[skill]` param accepts arbitrary strings | Low | Whitelist + `notFound()`. |
| R9 | Dashboard becomes a dumping ground | Low | Constrain to: overall band, 4 skill tiles, weak areas, recent activity, one next-action. Resist growth. |

---

## 14. Migration Strategy

Five phases, each independently shippable, app working throughout.

**Phase A — Cleanup and truth-telling (no user-visible change).**
Delete the duplicate `/cv/upload` route; delete `evaluateEssay`; resolve `/api/profile/update-scores` (§10); fix the user-scoping in `find_cached_evaluation`. Nothing moves. This clears the misleading ground before anyone builds on it.

**Phase B — Backend enablement (no user-visible change).**
Add the two exam proxy routes (outside the paid group); add the writing essays list endpoint + gateway route; migrations D1/D3. All additive, all independently testable. At the end of this phase every piece of data the new UI needs is reachable from the browser.

**Phase C — Onboarding.**
Remove `CvUploadStep`, 4 steps → 3, redirect to `/dashboard` (which by now must exist — so either sequence a stub `/dashboard` early in this phase or keep `/opportunities` until Phase E). Smallest, most self-contained change, zero backend dependency. Could ship first if you want an early win.

**Phase D — IELTS restructure.** *The large one.*
D1: extract `EssayComposer`/`WritingEvaluationPanel` and `SpeakingSessionPanel` into self-contained containers, still mounted inside Chat. Verify chat is unchanged.
D2: build `/ielts`, `/ielts/[skill]` with tabs, `/ielts/[skill]/session/[id]`.
D3: move exam shell/results; add redirects.
D4: repoint Chat's practice buttons; delete the now-dead mode state from `ChatShell`.
D5: sidebar `NAV_ITEMS` rewrite + section headers.
Each sub-step is a separate PR.

**Phase E — New surfaces.**
`/dashboard` and `/cv-review`; move `RequirePaid` from cv/upload to cv/review; add the CV prompt cards to Dashboard and Profile.

**Phase F — Polish.**
Unavailable-state copy for the empty tabs, upgrade-flow consolidation, rate-limit messaging, e2e sweep.

---

## 15. Recommended Implementation Order

Ranked by value delivered per unit of risk:

| # | Work | Phase | Effort | Risk | Why here |
|---|---|---|---|---|---|
| 1 | Cleanup: dead routes, phantom endpoint, cache scoping | A | S | Low | Removes three pieces of misinformation before anyone builds on them. Fixes a live 404. |
| 2 | Onboarding 4 → 3 steps | C | S | Low | Your clearest win. Self-contained, no backend, immediately better for every new free user. |
| 3 | Backend enablement: exam history/weak-areas routes, writing essays list, D1/D3 | B | M | Low | Unblocks everything downstream; ships invisibly; each endpoint testable alone. |
| 4 | Extract practice components out of `ChatShell` | D1 | M | **High** | The riskiest item, done while Chat still mounts them so regressions surface immediately. |
| 5 | `/ielts` + `/ielts/[skill]` + history detail | D2–D3 | L | Med | The centrepiece. Needs 3 and 4 first. |
| 6 | Sidebar rewrite + redirects + Chat handoff | D4–D5 | S | Med | Only after the destinations exist. |
| 7 | `/dashboard` | E | M | Low | Depends on 3. Becomes the onboarding target. |
| 8 | `/cv-review` + paywall move | E | M | Low | Turns the sidebar's one dead control into a real destination. |
| 9 | States, upgrade consolidation, e2e sweep | F | M | Low | Meaningful only once 1–8 exist. |

**Fast path if you want visible progress early:** items 1, 2, and 8 alone — cleanup, shorter onboarding, and a working CV Review page — are low-risk, need no restructure, and remove the two things a new user currently hits first (a paywalled onboarding step and a dead sidebar item).

---

## Open Questions

1. **Skill-first (`/ielts/[skill]` with tabs) or mode-first (your `/practice` section)?** I recommend skill-first for the reasons in §4.1, but it is your call and the mode-first version is still a clear improvement over today.
2. **`/api/profile/update-scores`** — delete the calls, or build the endpoint? Depends on whether programme matching needs the band on the user profile rather than in `exam_results`. Needs input from whoever owns RAG matching.
3. **Should exam history be free to read?** I think yes (R4), which means splitting the `/api/exam` paid group.
4. **Free-tier CV upload** — allow-upload-block-review (my recommendation) or block-upload? The former needs a gateway change and an upload rate limit.
5. **Resumable practice sessions** — you listed "continue previous sessions if applicable." Neither schema supports it today (§9.1). Confirm you are happy to defer it; if not, it becomes a schema project of its own.
6. **Reading and Listening Practice** — do we build them, or ship honest empty tabs? A skill-first IA makes the gap visible either way, which is why I raise it here rather than letting the layout decide it silently.
7. **Chat's conversational practice entry** — evaluate inline and link to history (my recommendation, §8.5), or navigate the user to the practice page mid-conversation?

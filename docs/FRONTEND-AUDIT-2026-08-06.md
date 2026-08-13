# GOA Frontend — Complete Pre-Ship Audit

**Date:** 2026-08-06
**Scope:** `services/frontend` (Next.js 16 App Router, React 19, Tailwind 4)
**Compared against:** `services/gateway/server.go` (the only browser-facing route surface), all 9 backing services, `docs/SCOPE-REDUCTION-PLAN.md`, `docs/IA-REDESIGN-PROPOSAL.md`, `docs/dorgham-context/implementation-plan/demo-readiness-plan/`
**Method:** every route, component, hook, lib module and gateway endpoint read directly. `tsc --noEmit` run clean.

---

## 0. Executive summary

**This frontend is in much better shape than a "finish the frontend" request implies.** The code quality is genuinely high — comments explain *why*, error taxonomies are modelled properly (`SubscriptionRequiredError`, `ProfileNotReadyError`, `RateLimitedError`), loading/empty/error states are present on nearly every screen, the design system is real, and TypeScript compiles clean with essentially no `any`.

The remaining work is **not "build missing pages."** It is four specific things:

1. **Three finished backend features have zero frontend consumers** — notifications, exam history, weak-areas. All three are wired end-to-end through the Gateway and are one page away from working.
2. **Two exam-integrity defects** that will bite during a live demo — Reading answers are not persisted (a refresh destroys the attempt), and Reading results live only in `sessionStorage` (unrecoverable after the tab closes).
3. **Realtime has no failure handling.** The Speaking WebSocket cannot reconnect and silently strands the UI on abnormal close; no stream anywhere can be cancelled by the user.
4. **A hardcoded "Free plan" badge and an upgrade CTA that leads nowhere** — the single most visible correctness bug on every authenticated page.

Everything else is polish. **Estimated remaining effort: 4.5–6 engineer-days** to demo-solid, ~11 days to production-solid.

**Do not build:** Stripe/billing, Listening exam, Speaking exam mode, pricing checkout. `docs/SCOPE-REDUCTION-PLAN.md` §1 cut all of these deliberately and the backend has **zero** Stripe code (verified by grep across all services). Building frontend for them would be building against nothing.

| Dimension | Demo | Production |
|---|---|---|
| UI completeness | 8.5 / 10 | 7.5 / 10 |
| Backend integration | 7.5 / 10 | 7.5 / 10 |
| UX | 8 / 10 | 7 / 10 |
| Reliability | 5.5 / 10 | 4 / 10 |
| Accessibility | 6.5 / 10 | 5.5 / 10 |
| Performance | 7.5 / 10 | 7 / 10 |
| **Overall** | **7.4 / 10** | **6.2 / 10** |

---

# PHASE 1–2 — Product model & screen inventory

## 1.1 Architecture as built

```
Browser (Next.js :3000)
   │  HttpOnly cookies (access_token / refresh_token), credentials:"include"
   ▼
Gateway (Go/Fiber :8080)  ← the ONLY host the browser talks to
   │  JWT · rate limit (60/min) · AI quotas · subscription gate · correlation IDs
   ├─ User (NestJS)        auth, profile, subscription tier
   ├─ Orchestration (Py)   /api/chat SSE, chat history, memory erase
   ├─ RAG (Py)             opportunity match, checklists, financial reqs
   ├─ Writing (Py)         essays, CV upload/review (SSE)
   ├─ Exam (Py)            sessions, reading/writing submit, progress, history
   ├─ Speaking (Go)        WebSocket proxy, session history, share links
   └─ Notification (Node)  GET /api/notifications   ← NO FRONTEND CONSUMER
```

**Frontend state model:** deliberately no global store. Every widget/page owns its own `useState` + a `use*` hook. `lib/request-dedupe.ts` collapses genuinely-concurrent duplicate GETs. There is no react-query, no SWR, no cache — every navigation refetches. This is a documented trade-off (`components/dashboard/index.ts`) and it is *fine at this scale*, but see §10.3 for the cost.

**Folder structure:** `app/` (routes + hooks + types), `components/` (by feature + `ui/` primitives), `lib/` (API clients + pure logic). Clean and consistent. One oddity: hooks and types live under `app/` rather than at the root — harmless, but it means `app/` is not purely routable.

## 1.2 Screen inventory

| # | Route | Purpose | Backend dependency | Status |
|---|---|---|---|---|
| 1 | `/` | Marketing landing (9 sections, server-rendered) | cookie read only | ✅ Complete |
| 2 | `/login` | Sign in + redirect-aware | `POST /auth/login`, `GET /api/profile` | ✅ Complete |
| 3 | `/register` | Create account | `POST /users` | ✅ Complete |
| 4 | `/forgot-password` | Request reset link | `POST /auth/forgot-password` | ✅ Complete |
| 5 | `/reset-password` | Confirm reset | `POST /auth/reset-password` | ✅ Complete |
| 6 | `/verify-email/[token]` | Email verification | `GET /auth/verify-email/:token` | ✅ Complete |
| 7 | `/onboarding` | 3-step wizard, URL-stepped, draft-persisted | `PUT /api/profile` | 🟡 Partial — 5 collected fields have no backend column |
| 8 | `/dashboard` | 7-widget home | profile, exam progress, speaking, writing | ✅ Complete |
| 9 | `/chat` | SSE assistant + intent routing | `POST /api/chat`, history, memory | 🟡 Partial — no stop button, no session list |
| 10 | `/opportunities` | Ranked programme matching, sort+filter | `POST /api/opportunities/query` | ✅ Complete — best page in the app |
| 11 | `/checklists` | Checklist index (localStorage-backed) | opportunities query | 🟡 Partial — index is client-only |
| 12 | `/checklist/[programId]` | Per-programme checklist + financials | `GET/PUT /api/checklists/*` | ✅ Complete |
| 13 | `/cv-review` | Upload + polled processing + SSE review | `/api/writing/cv/*` | ✅ Complete |
| 14 | `/profile` | View/edit academic profile | `GET/PUT /api/profile` | ✅ Complete |
| 15 | `/practice` | Practice section landing | none | ✅ Complete |
| 16 | `/practice/writing` | Essay composer + streamed evaluation | `essays/upload`, `essays/:id/evaluate` | 🟡 Partial — `isPaidTier` hardcoded `true` |
| 17 | `/practice/writing/history` | Essay list | `GET /api/writing/essays` | 🟡 Partial — no pagination/filter/detail |
| 18 | `/practice/speaking` | Live mic + WS + evaluation | `GET /api/speaking/ws` | 🟡 Partial — 1 hardcoded prompt, no reconnect |
| 19 | `/practice/speaking/history` | Sessions + band trend chart | `GET /api/speaking/sessions` | 🟡 Partial — no pagination/filter |
| 20 | `/practice/speaking/history/[id]` | Session detail + share | `GET /api/speaking/sessions/:id` | 🟡 Partial — no audio playback |
| 21 | `/speaking/share/[token]` | Public shared session | `GET /speaking/sessions/public/:token` | ✅ Complete |
| 22 | `/exam` | Skill picker + resume + progress | `POST /api/exam/sessions`, `/progress` | ✅ Complete |
| 23 | `/exam/shell` | Timed exam runner (Reading, Writing) | session, submit, heartbeat | 🟡 Partial — see §3.9, no answer persistence |
| 24 | `/exam/results` | Reading / Writing / generic results | `sessionStorage` (Reading), `/result` | 🟡 Partial — Reading results are ephemeral |
| 25 | `/design-system` | Component reference | none | ⚠️ Ships publicly in production |
| 26 | `/speaking`, `/speaking/history*` | Legacy redirects | none | ✅ Complete |
| — | **`/notifications`** | In-app notification list | `GET /api/notifications` **exists** | 🔴 **Missing** |
| — | **`/exam/history`** | Past attempts + weak areas | `GET /api/exam/history`, `/weak-areas` **exist** | 🔴 **Missing** |
| — | **`/settings`** | Account: delete, export, logout-all | 3 endpoints **exist** | 🔴 **Missing** |
| — | `/pricing`, `/billing` | Checkout | **no backend at all** | ⛔ Out of scope (cut) |

**26 routes built. 3 genuinely missing (all backend-ready). 2 deliberately cut.**

---

# PHASE 3 — Screen-by-screen findings

Only defects are listed. Anything not mentioned was inspected and is fine.

### 3.1 Global (affects every authenticated page)

| ID | Finding | Severity |
|---|---|---|
| **G1** | `components/ui/sidebar.tsx:317-320` renders **"Free plan" and "Unlock GOA Pro" unconditionally**. `useCurrentUser()` is already called four lines above and carries `subscriptionTier`. A paying subscriber sees an upgrade advert on every page. | 🔴 Critical |
| **G2** | `DEFAULT_UPGRADE_URL = "/#pricing"` (`lib/subscription.ts:26`). Every Upgrade CTA — sidebar, upgrade dialog, six paid-feature prompts — lands on a **marketing pricing section with no purchase path**. From an authenticated page it also dumps the user out of the app shell entirely. | 🔴 Critical |
| **G3** | The skip link in `app/layout.tsx:78` targets `#main-content`, which exists on **only 2 of 26 routes** (`/`, `/design-system`). On every authenticated page the skip link focuses nothing. `app/(app)/layout.tsx:895` renders a `<div>`, not `<main>`. | 🟠 High (a11y) |
| **G4** | **No toast/notification system anywhere.** Every transient outcome is an inline `<Alert>` or nothing. Successful profile saves, checklist toggles, share-link copies have no ambient confirmation. | 🟡 Medium |
| **G5** | `useCurrentUser()` mounts in the Sidebar **plus** 3 dashboard widgets **plus** the page itself. `request-dedupe` collapses the concurrent burst, but every client-side navigation refetches the profile from scratch. No cache, no `staleTime`. | 🟡 Medium |
| **G6** | `/design-system` (600 lines) is **not in `middleware.ts`'s matcher** and is publicly reachable in production. | 🟡 Medium |
| **G7** | `lib/current-user.ts` still exports `CURRENT_USER_ID = "user-lina"`, used as a live fallback in `chat-shell.tsx:138` and `speaking-practice-panel.tsx:60`. If `GET /api/profile` fails, chat and speaking sessions are attributed to a **fictional user id**. | 🟠 High |

### 3.2 `/chat`

- **C1 🟠** No **stop-generation** control. `chatAbortRef` exists and works — it is only wired to unmount and "New conversation". A user watching a wrong 60-second answer stream has no way to interrupt it. ~30 min to expose.
- **C2 🟡** No **chat session list**. `sessionStorage` holds exactly one id; "New conversation" destroys access to the previous thread forever, even though `GET /api/chat/sessions/:id/history` can retrieve any of them.
- **C3 🟡** `"Sync Ready"` with a pulsing green dot (`chat-shell.tsx:583`) is **static decoration** — it is not bound to any connection state. It reads as a status indicator and lies.
- **C4 🟡** "Forget what you know about me" uses `window.confirm()` for a **destructive, irreversible** action, while the app has a proper `Modal` primitive.
- **C5 🟡** No per-message **copy / retry / regenerate**. `useClipboard` hook exists and is unused here.
- **C6 🟡** No **SSE idle timeout**. If Orchestration accepts the connection and then stalls, the typing indicator spins indefinitely.

### 3.3 `/dashboard`
- **D1 🟢** `RecommendationsWidget` returns `null` on `status !== "success"` — a Free-tier user (403 → `upgrade-required`) sees the widget vanish with no explanation of *why*.
- **D2 🟢** `RecentActivityWidget` links every writing row to the history *list* because no essay detail page exists. Honest, but a dead-feeling click.

### 3.4 `/opportunities`
Best-executed page in the codebase — 6 distinct states, abort-guarded, sort + filter, honest disclaimer. Two nits:
- **O1 🟢** No **URL state** for `sort`/`filter` — a shared or refreshed URL loses the view.
- **O2 🟢** No pagination or virtualisation. Fine at ~30 seeded programmes; degrades past a few hundred.

### 3.5 `/checklists`
- **CL1 🟠** The index is backed by **`localStorage` only** (`lib/checklist-index.ts`). Sign in on a second device or clear site data and every checklist disappears from the UI while remaining on the server. Blocked on a backend `GET /api/checklists` list endpoint — see §14.
- **CL2 🟢** "Remove" has no confirmation. Copy is honest ("the checklist itself is kept"), so this is low-risk.

### 3.6 `/cv-review`
- **CV1 🟢** Polling `GET /cv/latest` every 4 s has **no maximum attempt count** — a CV stuck in `processing` polls forever.
- **CV2 🟢** "Review history isn't available yet" is an honest empty state for a real backend gap (§14).

### 3.7 `/practice/writing`
- **W1 🟠** `isPaidTier` is **hardcoded `true`** (`writing-practice-panel.tsx:38`, with its own `TODO`). Paid-only sections of the evaluation panel render for Free users, who then hit a 403 they were shown UI for.
- **W2 🟡** `streamWritingEvaluation` accepts **no `AbortSignal`**. Navigating away mid-evaluation leaves the reader running and `setState` firing on an unmounted component.
- **W3 🟡** No word count, no timer, no task-type selector — always `"task2"`.

### 3.8 `/practice/speaking`
- **S1 🔴** `SpeakingWebSocket` has **no reconnect, no backoff, no heartbeat/ping**. `onclose` handles **only code 1008**; a 1006 abnormal close (the common one) leaves the UI in `transcribing`/`evaluating` with no error until the 15 s transcription timeout — and if the socket dies during `evaluating`, **nothing ever resolves**.
- **S2 🟠** No **tier check before opening the socket**. The exam page short-circuits on `subscriptionTier !== "paid"`; speaking does not, so a Free user grants mic permission, records, and then gets a raw close.
- **S3 🟠** **One hardcoded prompt** — `"Describe a memorable journey you have taken."` No question bank, no Part 1/3, no 60-second prep timer, no max recording duration.
- **S4 🟡** No mic **level meter or device picker** before recording; a muted mic is only discovered after a full take.
- **S5 🟡** No audio playback of your own recording on the detail page.

### 3.9 `/exam/shell` — the highest-risk screen

- **E1 🔴 CRITICAL** **Reading answers are never persisted.** `ReadingExam` holds them in `useReducer` memory only. A refresh, crash, or accidental back-navigation **destroys 60 minutes of work**, and the heartbeat keeps telling the server the session is alive. Fix: debounced write to `sessionStorage`, rehydrate in `buildInitialState`. **~1 hour. This is the single highest-value fix in the audit.**
- **E2 🔴 CRITICAL** **Reading results are `sessionStorage`-only** (`lib/reading-result-storage.ts`). There is no `GET` result endpoint for Reading, so closing the tab makes a completed, graded exam **permanently unviewable**. Requires a backend endpoint (§14) — mitigate now by warning before navigating away.
- **E3 🟠** `loadSession` failure does a **silent `router.push("/exam")`** (`shell/page.tsx:90-93`) with only a `console.error`. The user is teleported out of their exam with no explanation.
- **E4 🟠** **`md:hidden` full-screen "EXAM MODE LOCKED"** blocks the exam below 768px with a hard, unstyled grey wall. Defensible for a real IELTS simulation, but it is a raw dead end — no "continue anyway", no link out, and it will be hit on a phone during a demo.
- **E5 🟡** The generic submit modal is a **bespoke `fixed inset-0` div**, not the `Modal` primitive — no focus trap, no Escape, no `role="dialog"`.
- **E6 🟡** `submissionError` renders *inside* `<main>` below the exam content — on a long Reading page it appears far below the fold, invisible at the moment it matters.
- **E7 🟡** Heartbeat failures are **silently swallowed** (`sendHeartbeat` never throws, by design). Nine consecutive failures silently forfeit the attempt with zero user signal.
- **E8 🟢** No `beforeunload` guard on an in-progress exam.

### 3.10 `/exam/results`
- **R1 🟡** Reading branch shows `"No Reading result found for this session."` with **no recovery action** — no link back, no explanation that results are session-scoped.
- **R2 🟢** Three separate `"No result found."` bare-text terminal states with no actions.

### 3.11 `/onboarding`
- **ON1 🟡** Five collected fields (university, graduation year, target degree/major/intake, target IELTS score) are **collected and silently discarded** — no backend column. Already documented in the code; still a user-visible lie about what gets saved.
- **ON2 🟢** `setTimeout(…, 1100)` before `window.location.assign` — a fixed delay masquerading as a completion animation.

---

# PHASE 4 — Component audit

**23 UI primitives, ~60 feature components.** The design system is real and consistently used: `Button`, `Card`, `Alert`, `EmptyState`, `Skeleton`, `Progress`, `Modal`, `Field`, `Combobox`, `Tabs`, `Tooltip`, all with a server/client boundary documented in `components/ui/index.ts` and enforced by a unit test (`ui-server-boundary.test.ts`).

| Finding | Detail |
|---|---|
| **Dead code** | **None.** Every module under `components/`, `lib/`, `app/hooks/` is referenced. The only unreferenced files are three `.test.ts` files (expected). This is unusually clean. |
| **Duplicate modal** | Exam shell (`shell/page.tsx:330`) and `SubmitConfirmModal` hand-roll dialogs instead of using `Modal`. Two of three dialog implementations lack focus trapping. |
| **Duplicate error card** | `/exam/results` renders a bespoke error `Card` where every other page uses `<Alert tone="danger" actions={…}>`. |
| **Duplicate types** | `Opportunity` is declared identically in `chat-shell.tsx:34` and `chat-stream.ts:5`, and again as `MatchedProgram` in `opportunities-api.ts`. Three copies of one shape. |
| **Oversized** | `chat-shell.tsx` (645) — should split state machine from view. `cv-review/page.tsx` (521), `exam/page.tsx` (466), `sidebar.tsx` (458), `combobox.tsx` (451). |
| **Missing loading variants** | `Button` has `loading`/`loadingLabel` ✅. `Card`, `EmptyState`, `Progress` have none — pages hand-roll `Skeleton` wrappers. |
| **Props validation** | TypeScript only, no runtime validation. Acceptable. |
| **A11y gaps** | `EssayComposer`/`ChatInput` textareas — verify `aria-describedby` for counters. Custom `<button>` toggle rows use `aria-expanded` ✅. Reading question components need a keyboard-navigation pass. |

---

# PHASE 5 — Backend integration audit

Every route registered in `services/gateway/server.go`, against every call site in the frontend.

| # | Endpoint | Used? | Notes |
|---|---|---|---|
| 1 | `POST /users` | ✅ YES | `authApi.register` |
| 2 | `POST /auth/login` | ✅ YES | |
| 3 | `POST /auth/refresh` | 🔴 **NO** | **No refresh flow exists client-side.** When the access token expires mid-session the user gets 401s with no recovery — pages simply start failing. Needs an axios/fetch interceptor. |
| 4 | `POST /auth/forgot-password` | ✅ YES | |
| 5 | `POST /auth/reset-password` | ✅ YES | |
| 6 | `GET /auth/verify-email/:token` | ✅ YES | |
| 7 | `POST /auth/logout` | ✅ YES | |
| 8 | `POST /auth/logout-all` | 🔴 NO | Needs `/settings` → "Sign out everywhere" |
| 9 | `DELETE /users/:id/account` | 🔴 NO | Needs `/settings` → account deletion. **GDPR-relevant.** |
| 10 | `GET /users/:id/data-export` | 🔴 NO | Needs `/settings` → data export. **GDPR-relevant.** |
| 11 | `POST /api/writing/essays/upload` | ✅ YES | `writing-practice-api` |
| 12 | `POST /api/writing/cv/upload` | ✅ YES | cv-review + `authApi.uploadCv` (the latter is now dead — onboarding CV step was removed) |
| 13 | `GET /api/writing/cv/latest` | ✅ YES | polled |
| 14 | `POST /api/writing/cv/review` | ✅ YES | SSE |
| 15 | `GET /api/writing/essays` | 🟡 PARTIAL | Called with **no arguments**. `listEssays` supports `page` and `submissionType`; the history page passes neither, so only page 1 is ever reachable. |
| 16 | `POST /api/writing/essays/:id/evaluate` | ✅ YES | SSE |
| 17 | `POST /api/chat` | ✅ YES | SSE |
| 18 | `GET /api/chat/sessions/:id/history` | 🟡 PARTIAL | Only ever called for the *current* `sessionStorage` id. Any other session is unreachable — no session picker. |
| 19 | `DELETE /api/sessions/memory` | ✅ YES | |
| 20 | `POST /api/exam/sessions` | ✅ YES | |
| 21 | `GET /api/exam/listening/start` | ⛔ NO | Listening cut (SCOPE-REDUCTION §1) |
| 22 | `PUT /api/exam/listening/:id/submit` | ⛔ NO | Listening cut |
| 23 | `PUT /api/exam/sessions/:id/submit` | ✅ YES | generic + writing task |
| 24 | `PUT /api/exam/reading/:id/submit` | ✅ YES | |
| 25 | `GET /api/exam/sessions/:id/result` | ✅ YES | writing + generic |
| 26 | `GET /api/exam/sessions/:id` | ✅ YES | |
| 27 | `PATCH /api/exam/sessions/:id/heartbeat` | ✅ YES | 60 s interval |
| 28 | `GET /api/exam/progress` | ✅ YES | exam page + 2 dashboard widgets |
| 29 | **`GET /api/exam/history`** | 🔴 **NO** | **Finished backend, paginated, no consumer.** Should feed an `/exam/history` page. |
| 30 | **`GET /api/exam/weak-areas`** | 🔴 **NO** | **Finished backend, no consumer.** Should feed the exam page's "Practice focus" card, which currently derives a weakest skill client-side from `/progress` instead. |
| 31 | `GET /api/notifications` | 🔴 **NO** | **A whole service (SQS + SES + DB + local-server + gateway route) with zero frontend.** Highest-visibility disconnected feature in the project. |
| 32 | `GET /api/speaking/sessions` | 🟡 PARTIAL | No pagination params sent |
| 33 | `GET /api/speaking/sessions/:id` | ✅ YES | |
| 34 | `POST /api/speaking/sessions/:id/share` | ✅ YES | |
| 35 | `GET /api/speaking/ws` | ✅ YES | see §6 |
| 36 | `GET /speaking/sessions/public/:token` | ✅ YES | |
| 37 | `POST /api/opportunities/query` | ✅ YES | opportunities + checklists |
| 38 | `GET /api/checklists/:programId` | ✅ YES | |
| 39 | `PUT /api/checklists/:programId/items/:itemId` | ✅ YES | optimistic ✅ |
| 40 | `GET /api/checklists/:programId/financial` | ✅ YES | |
| 41 | `GET /api/profile` | ✅ YES | heavily |
| 42 | `PUT /api/profile` | ✅ YES | |
| 43 | `GET /api/ping` | — | health probe |
| 44 | `POST /api/admin/ingestion/run`, `GET /admin/costs` | — | admin-key, correctly not in the browser |

**Score: 30 fully consumed / 4 partial / 8 unconsumed (3 of which are real gaps, 2 cut, 3 need a settings page).**

### Mock / fake / hardcoded data

**There is no mock data and no fake API in this frontend.** Every number on screen comes from a real endpoint. That is a notable result — the demo-readiness plan's "remove fabricated results content" work clearly landed. The remaining hardcoded values are:

| Location | Value | Impact |
|---|---|---|
| `sidebar.tsx:319` | `"Free plan"` | 🔴 Wrong for paying users |
| `lib/subscription.ts:26` | `"/#pricing"` | 🔴 CTA leads nowhere |
| `writing-practice-panel.tsx:38` | `isPaidTier = true` | 🟠 Free users shown paid UI |
| `lib/current-user.ts` | `"user-lina"` | 🟠 Fallback identity |
| `speaking-practice-panel.tsx:64` | one speaking prompt | 🟠 No question bank |
| `chat-shell.tsx:583` | `"Sync Ready"` | 🟡 Fake status indicator |
| `exam/page.tsx:170-257` | 4 skill cards + colours | 🟢 Correct — static product copy |

---

# PHASE 6 — WebSocket & SSE audit

### SSE (chat, writing evaluation, CV review)

`SSEParser` in `lib/chat-stream.ts` is well-built: shared across all three producers, handles CRLF framing (sse-starlette), flushes the trailing frame, tolerates malformed JSON per-frame.

| | Chat | Writing eval | CV review |
|---|---|---|---|
| Abort support | ✅ `AbortController` | 🔴 none | 🔴 none |
| User-facing cancel | 🔴 none | 🔴 none | 🔴 none |
| Idle/stall timeout | 🔴 none | 🔴 none | 🔴 none |
| Reconnect / resume | 🔴 none | 🔴 none | 🔴 none |
| Auth (`credentials`) | ✅ | ✅ | ✅ |
| Paywall 403 handling | ✅ | ✅ | ✅ |
| Empty-stream guard | ✅ | 🔴 none | 🔴 none |

A stalled upstream on any of the three produces an **indefinite spinner**. Chat has the machinery (`chatAbortRef`) and just needs a button; writing and CV need `signal` threaded through.

### WebSocket (speaking)

`lib/speaking-websocket.ts` — 165 lines, no resilience layer at all.

| Concern | Status |
|---|---|
| Reconnect | 🔴 None |
| Exponential backoff | 🔴 None |
| Heartbeat / ping-pong | 🔴 None |
| Abnormal close (1006) | 🔴 **Unhandled** — only 1008 is |
| Send queue while `CONNECTING` | 🔴 Audio chunks **silently dropped** (`sendAudio` returns early) |
| Connection timeout | 🔴 None — `connecting` can hang forever |
| Evaluation timeout | 🟡 15 s exists on `processing`, **none on `evaluating`** |
| `JSON.parse(event.data)` | 🔴 **Unguarded** — a malformed text frame throws inside `onmessage` |
| Binary TTS | ✅ Blob + ArrayBuffer both handled |
| Cleanup on unmount | ✅ Correct |

The realistic failure — the Gateway proxy or Speaking service dropping the connection mid-evaluation — leaves the user staring at a spinner with a dead socket and no error. **This is the second-most-likely thing to break in a live demo.**

---

# PHASE 7 — Feature completeness

| Feature | Production ready? | What's missing |
|---|---|---|
| Registration | ✅ Yes | — |
| Login | ✅ Yes | — |
| Logout | ✅ Yes | No "sign out everywhere" (endpoint exists) |
| Forgot / reset password | ✅ Yes | — |
| Email verification | ✅ Yes | No "resend" (no backend endpoint) |
| **Token refresh** | 🔴 **No** | **Endpoint exists, no client interceptor.** Session silently dies. |
| Onboarding | 🟡 Nearly | 5 fields discarded; no "why we ask" per field |
| Dashboard | ✅ Yes | Free-tier widgets vanish silently |
| Profile | ✅ Yes | — |
| **Account settings** | 🔴 **Missing** | Delete account, data export, logout-all — **3 endpoints ready, 0 UI** |
| Chat | 🟡 Nearly | Stop button, session list, real sync indicator |
| Opportunity matching | ✅ Yes | URL state for filters |
| Opportunity details | 🟡 Partial | No per-programme detail page — card + checklist only |
| Application checklist | ✅ Yes | Server-side index (backend gap) |
| CV review | ✅ Yes | No review history (backend gap); unbounded poll |
| Writing practice | 🟡 Nearly | `isPaidTier` hardcoded, no cancel, no word count |
| Writing history | 🟡 Partial | No pagination/filter/sort/search/detail |
| Speaking practice | 🟡 Partial | No reconnect, 1 prompt, no tier gate, no prep timer |
| Speaking history | 🟡 Partial | No pagination/filter; no audio playback |
| Reading exam | 🟠 **Risky** | **No answer persistence**, no results persistence |
| Writing exam | ✅ Yes | Per-task submit + combined results work well |
| Listening exam | ⛔ Cut | Also blocked: no audio-URL endpoint (gateway TODO line 258) |
| Speaking exam | ⛔ Cut | — |
| Exam dashboard | ✅ Yes | `/exam` covers it |
| **Exam history** | 🔴 **Missing** | **`GET /api/exam/history` ready, 0 UI** |
| Exam results | 🟡 Partial | Reading results ephemeral |
| **Notifications** | 🔴 **Missing** | **Whole service ready, 0 UI** |
| Subscription gate | 🟡 Partial | Gate + dialog excellent; **upgrade goes nowhere**, badge hardcoded |
| Pricing / Billing / Stripe | ⛔ Cut | **No backend exists.** Do not build. |

---

# PHASE 8 — History audit

| Page | Pagination | Filter | Sort | Search | Loading | Empty | Error | Detail | API |
|---|---|---|---|---|---|---|---|---|---|
| Writing History | 🔴 (API supports it) | 🔴 (API supports it) | 🔴 | 🔴 | ✅ skeleton | ✅ | ✅ retry | 🔴 none | ✅ |
| Speaking History | 🔴 | 🔴 | 🔴 | 🔴 | ✅ skeleton | ✅ | ✅ retry | ✅ | ✅ |
| **Exam History** | — | — | — | — | — | — | — | — | 🔴 **page does not exist** |
| Chat History | 🔴 | 🔴 | 🔴 | 🔴 | 🔴 none | 🔴 | 🟡 console only | — | 🟡 current session only |
| Checklists | n/a | 🔴 | 🔴 | 🔴 | ✅ skeleton | ✅ | 🟡 partial | ✅ | 🟡 localStorage index |
| CV Review History | — | — | — | — | — | ✅ honest | — | — | 🔴 no backend |

Uniform pattern: **loading/empty/error are consistently good; pagination/filter/sort/search are uniformly absent.** `listEssays(page, submissionType)` already exists and is simply not called with arguments — that is a 1-hour fix, not a feature build.

---

# PHASE 9 — UX review

**Strengths (worth keeping):** honest empty states that explain *why* something is empty and what to do; error copy that never blames the user; `blockedReason()` translating internal gate ids into actionable sentences; the `SubscriptionRequiredError` → one shared dialog pattern; a genuine loading/empty/error triad on nearly every screen; reduced-motion respected in onboarding.

| # | Problem | Proposed fix |
|---|---|---|
| U1 | Upgrade CTA dead-ends at `/#pricing` | Build `/upgrade` inside the app shell: current tier, feature comparison, and (given no Stripe) a documented "request upgrade" or admin-flip flow. Repoint `DEFAULT_UPGRADE_URL`. |
| U2 | Free user's "Take Exam" → dialog → landing page → lost | Same fix; keep them in-shell. |
| U3 | No global success feedback | Add a `Toast` primitive + provider in `(app)/layout.tsx`. Unblocks ~8 silent success paths. |
| U4 | Exam mobile = grey wall | Style it on-brand, add "Back to exams", and detect on `/exam` *before* burning a session slot (the hourly limit is 3). |
| U5 | Reading refresh loses everything | Persist answers (E1). Add `beforeunload`. |
| U6 | Speaking: one prompt forever | Prompt rotation from a seeded local bank + "New prompt" button. Cheap, hugely improves the demo. |
| U7 | Writing history rows are inert | Make each row expand in place to show the stored evaluation. |
| U8 | Chat: can't stop a bad answer | Wire `chatAbortRef` to a Stop button. |
| U9 | Onboarding asks for data it throws away | Either remove those fields or label them "used in this session only". |
| U10 | Dashboard widgets silently disappear for Free users | Render an upgrade nudge instead of `null` (IeltsSummaryWidget already does this — copy that pattern to Recommendations). |
| U11 | Filters not in the URL | `useSearchParams` for `sort`/`filter` on `/opportunities`. |
| U12 | No breadcrumbs on nested detail routes | Back links exist on most; standardise. |

**Mobile:** the app shell, sidebar drawer, marketing page and auth pages are properly responsive (the `flex-col lg:flex-row` fix in `(app)/layout.tsx` is documented and correct). The exam shell is the only hard-blocked surface.

---

# PHASE 10 — Code quality

**Genuinely good.** `tsc --noEmit` passes clean. No `any`, no `@ts-ignore`, no `@ts-expect-error`, no `console.log` in shipped code, no dead modules.

| Issue | Detail |
|---|---|
| 🔴 **No ESLint config at all** | No `eslint.config.*`, no `.eslintrc`, no `lint` script in `package.json`. `next lint` was never wired. Exhaustive-deps violations are unchecked (there is already a manual `eslint-disable-next-line react-hooks/exhaustive-deps` in `writing-practice-panel.tsx` for a rule that isn't running). |
| 🔴 **Frontend is absent from CI** | `.github/workflows/ci.yml` `detect-changes` filters cover 9 services — **`services/frontend` is not one of them**. 22 unit test files and 13 Playwright specs **never run on any PR**. |
| 🟡 No `typecheck` script | `tsc --noEmit` passes but nothing enforces it. |
| 🟡 3 TODOs | `writing-practice-panel.tsx:38` (real bug), 2× stimulus-image TODOs (documented decision — should be closed out per SCOPE-REDUCTION §2). |
| 🟡 Commented-out import | `exam/shell/page.tsx:13` — `// import { evaluateEssay }` |
| 🟡 Type duplication | `Opportunity` × 3 (see Phase 4) |
| 🟡 `console.error` × ~15 | Fine for dev; no error-reporting sink for production |
| 🟡 Large files | `chat-shell.tsx` 645, `design-system/page.tsx` 600, `cv-review/page.tsx` 521 |
| 🟢 Repo hygiene | The 1.7 MB Trello export and tracked TypeScript build-info artifacts were identified for removal. The Trello export was removed during the repository cleanup. |

---

# PHASE 11 — Production readiness

### 🔴 Critical (must fix before anyone relies on this)
1. **E1** Reading exam answers not persisted — data loss on refresh
2. **E2** Reading results `sessionStorage`-only — completed exams unrecoverable
3. **#3** No token-refresh interceptor — sessions silently die mid-use
4. **G1** "Free plan" hardcoded — paying users advertised at
5. **G2** Upgrade CTA leads nowhere — the paid tier cannot be purchased or requested
6. **S1** Speaking WS has no reconnect / no abnormal-close handling — silent hang
7. **CI** Frontend excluded from CI — 35 test files never execute

### 🟠 High
8. **#31** Notifications: complete backend, no UI
9. **#29/#30** Exam history + weak-areas: complete backend, no UI
10. **#8/#9/#10** No settings page — account deletion & data export unreachable (GDPR)
11. **G7** `"user-lina"` fallback identity in live code paths
12. **W1** `isPaidTier` hardcoded true
13. **S2** No tier gate before mic permission
14. **G3** Skip link broken on 24/26 routes
15. **E3** Silent redirect out of a failed exam load
16. **No ESLint**

### 🟡 Medium
17. No toast system · 18. No stream cancellation (writing, CV) · 19. No SSE idle timeouts · 20. No chat session list · 21. History pagination unused · 22. `/design-system` public · 23. Fake "Sync Ready" · 24. `window.confirm` for destructive action · 25. Bespoke modals without focus trap · 26. Unbounded CV poll · 27. Checklist index device-local · 28. No error-reporting sink (Sentry) · 29. No refetch-on-focus / cache

### 🟢 Low
30. URL state for filters · 31. Type duplication · 32. Large files · 33. `beforeunload` guards · 34. Repo junk · 35. Commented-out import · 36. Onboarding fixed 1100 ms delay

---

# PHASE 12 — Implementation roadmap

Effort: **XS** <30 min · **S** 1–2 h · **M** half day · **L** 1 day · **XL** multi-day

## Milestone 1 — Exam integrity & data loss (🔴) · ~1 day

| # | Task | Eff | Why | Files |
|---|---|---|---|---|
| 1.1 | Persist Reading answers to `sessionStorage` (debounced) + rehydrate in `buildInitialState` | **S** | 60 min of work destroyed by one refresh | `components/reading/ReadingExam.tsx`, new `lib/reading-answer-storage.ts` |
| 1.2 | `beforeunload` guard while an exam is in progress | **XS** | Cheap insurance for 1.1 | `app/(app)/exam/shell/page.tsx` |
| 1.3 | Replace silent redirect on `loadSession` failure with an Alert + explicit "Back to exams" | **S** | E3 | `exam/shell/page.tsx` |
| 1.4 | Move `submissionError` into the sticky header; add retry | **S** | E6 | `exam/shell/page.tsx` |
| 1.5 | Surface repeated heartbeat failure as a warning banner | **S** | E7 — silent forfeiture | `lib/exam-api.ts`, `exam/shell/page.tsx` |
| 1.6 | Style the mobile exam block on-brand + exit link; detect on `/exam` before creating a session | **S** | E4, protects the 3/hour limit | `exam/shell/page.tsx`, `exam/page.tsx` |

## Milestone 2 — Auth & tier correctness (🔴) · ~1 day

| # | Task | Eff | Why | Files |
|---|---|---|---|---|
| 2.1 | Bind sidebar plan badge + Pro callout to `user.subscriptionTier` | **XS** | G1 — most visible bug in the app | `components/ui/sidebar.tsx` |
| 2.2 | Build `/upgrade` in-shell (tier, comparison, request-upgrade); repoint `DEFAULT_UPGRADE_URL` | **M** | G2 — closes the paid loop | new `app/(app)/upgrade/page.tsx`, `lib/subscription.ts` |
| 2.3 | Axios + fetch 401 interceptor → `POST /auth/refresh` → replay once → else `/login` | **M** | #3 — sessions die silently today | `lib/api.ts`, new `lib/fetch-with-auth.ts` |
| 2.4 | Delete `CURRENT_USER_ID`; block chat/speaking on unresolved identity instead | **S** | G7 | `lib/current-user.ts`, `chat-shell.tsx`, `speaking-practice-panel.tsx` |
| 2.5 | Wire `isPaidTier` to `useCurrentUser()` | **XS** | W1 | `components/practice/writing-practice-panel.tsx` |
| 2.6 | Tier check before opening the speaking socket (mirror `exam/page.tsx:101`) | **XS** | S2 | `speaking-practice-panel.tsx` |

**Dependency:** 2.2 before 2.1's CTA is meaningful.

## Milestone 3 — Connect the finished backends (🟠) · ~1.5 days

| # | Task | Eff | Why | Files |
|---|---|---|---|---|
| 3.1 | `lib/notifications-api.ts` + `useNotifications` + bell in sidebar + `/notifications` page | **M** | An entire built service with no UI | new `lib/notifications-api.ts`, `app/hooks/useNotifications.ts`, `app/(app)/notifications/page.tsx`, `components/ui/sidebar.tsx` |
| 3.2 | `/exam/history` page on `GET /api/exam/history` (paginated) | **M** | Built, paginated, unused | new `lib/exam-history-api.ts`, `app/(app)/exam/history/page.tsx` |
| 3.3 | Feed `GET /api/exam/weak-areas` into the exam page's "Practice focus" card | **S** | Replaces a client-side approximation with the real thing | `lib/exam-api.ts`, `exam/page.tsx` |
| 3.4 | `/settings`: delete account (typed confirm), data export, sign out everywhere | **M** | 3 endpoints ready; GDPR | new `app/(app)/settings/page.tsx`, `lib/api.ts` |
| 3.5 | Pass `page`/`submissionType` to `listEssays`; add "Load more" + type filter | **S** | API already supports it | `app/hooks/useWritingHistory.ts`, `practice/writing/history/page.tsx` |

## Milestone 4 — Realtime resilience (🔴/🟠) · ~1 day

| # | Task | Eff | Why | Files |
|---|---|---|---|---|
| 4.1 | Reconnect + exponential backoff + max attempts in `SpeakingWebSocket` | **M** | S1 | `lib/speaking-websocket.ts` |
| 4.2 | Handle all close codes; connection timeout; `evaluating` timeout; guard `JSON.parse` | **S** | S1 | `lib/speaking-websocket.ts` |
| 4.3 | Buffer audio chunks while `CONNECTING`, flush on open | **S** | Silent audio loss | `lib/speaking-websocket.ts` |
| 4.4 | Stop-generation button in chat (wire existing `chatAbortRef`) | **S** | C1 | `chat-shell.tsx`, `chat-input.tsx` |
| 4.5 | Thread `AbortSignal` through `streamWritingEvaluation` + `streamCvReview`; add cancel buttons | **S** | W2 | `lib/writing-stream.ts`, `lib/cv-api.ts`, both panels |
| 4.6 | Idle timeout (no event for N s → error + retry) in `SSEParser` consumers | **S** | Infinite spinners | `lib/chat-stream.ts` + 3 consumers |
| 4.7 | Cap CV polling at ~2 min, then "still processing — check back" | **XS** | CV1 | `cv-review/page.tsx` |

## Milestone 5 — UX & polish (🟡) · ~1 day

| 5.1 | `Toast` primitive + provider; adopt on ~8 silent success paths | **M** | `components/ui/toast.tsx`, `(app)/layout.tsx` |
| 5.2 | Replace `window.confirm` and the two bespoke exam modals with `Modal` | **S** | `chat-shell.tsx`, `exam/shell/page.tsx`, `SubmitConfirmModal.tsx` |
| 5.3 | Remove the fake "Sync Ready" or bind it to real stream state | **XS** | `chat-shell.tsx` |
| 5.4 | Speaking prompt bank (seeded local list) + "New prompt" | **S** | `speaking-practice-panel.tsx` |
| 5.5 | Expandable writing-history rows showing stored evaluation | **M** | `practice/writing/history/page.tsx` |
| 5.6 | Sort/filter in the URL on `/opportunities` | **S** | `opportunities/page.tsx` |
| 5.7 | Free-tier nudge instead of `null` in `RecommendationsWidget` | **XS** | `recommendations-widget.tsx` |
| 5.8 | Recovery actions on all "No result found" terminal states | **S** | `exam/results/page.tsx` |
| 5.9 | Remove or label the 5 discarded onboarding fields | **S** | `components/onboarding/*` |

## Milestone 6 — Accessibility · ~0.5 day

| 6.1 | `<main id="main-content">` in `(app)/layout.tsx` and `(auth)/layout.tsx` — fixes the skip link on 24 routes | **XS** |
| 6.2 | Focus trap + Escape + `role="dialog"` on the two hand-rolled modals (covered by 5.2) | — |
| 6.3 | Keyboard-navigation pass over Reading question components + `QuestionNavSidebar` | **M** |
| 6.4 | Verify `aria-live` on streaming chat/evaluation regions | **S** |
| 6.5 | Contrast audit of `text-fg-subtle` on `bg-canvas-subtle` | **S** |

## Milestone 7 — Production hardening · ~1 day

| 7.1 | Add `frontend` to `.github/workflows/ci.yml` `detect-changes` + a `test-frontend` job (`vitest run`, `tsc --noEmit`, `next build`) | **M** — **highest leverage item in this milestone** |
| 7.2 | ESLint flat config + `lint` script + `typecheck` script; fix fallout | **M** |
| 7.3 | Error-reporting sink (Sentry) wired into both `error.tsx` boundaries | **M** |
| 7.4 | Gate `/design-system` behind a non-production check | **XS** |
| 7.5 | Add `not-found.tsx` and per-route `loading.tsx` | **S** |
| 7.6 | Repo hygiene: remove the 1.7 MB Trello export and tracked `.tsbuildinfo` | **XS — Trello export resolved** |
| 7.7 | Consolidate the 3 `Opportunity` type declarations | **S** |
| 7.8 | Split `chat-shell.tsx` state machine out of the view | **M** |

---

# PHASE 13 — Frontend completion checklist

*Ordered in the exact sequence to implement.*

## Exam integrity — do first, highest risk
- [ ] Persist Reading exam answers to `sessionStorage`, rehydrate on mount
- [ ] `beforeunload` guard while an exam is in progress
- [ ] Replace the silent redirect on exam-session load failure with an explained error
- [ ] Move submission errors into the sticky exam header with a retry
- [ ] Surface repeated heartbeat failures as a visible warning
- [ ] Style the mobile exam block and detect it before creating a session

## Auth & tier
- [ ] Bind the sidebar plan badge and Pro callout to `subscriptionTier`
- [ ] Build the in-app `/upgrade` page; repoint `DEFAULT_UPGRADE_URL`
- [ ] Add the 401 → `POST /auth/refresh` → replay interceptor
- [ ] Delete `CURRENT_USER_ID` and block on unresolved identity
- [ ] Wire `isPaidTier` to the real profile in Writing Practice
- [ ] Tier-gate the speaking socket before requesting mic permission

## Backend connections (all endpoints already exist)
- [ ] Notifications: API client, hook, sidebar bell, `/notifications`
- [ ] `/exam/history` on `GET /api/exam/history`
- [ ] Weak-areas into the exam page's practice-focus card
- [ ] `/settings`: delete account, data export, sign out everywhere
- [ ] Writing history pagination + submission-type filter

## Realtime
- [ ] Speaking WS reconnect + backoff + max attempts
- [ ] Handle every close code; add connection and evaluation timeouts; guard `JSON.parse`
- [ ] Buffer audio while connecting
- [ ] Stop-generation button in chat
- [ ] `AbortSignal` + cancel for writing evaluation and CV review
- [ ] SSE idle timeouts on all three streams
- [ ] Cap CV status polling

## UX
- [ ] Toast primitive + provider; adopt on all silent success paths
- [ ] Replace `window.confirm` and both hand-rolled modals with `Modal`
- [ ] Remove the fake "Sync Ready" indicator
- [ ] Speaking prompt bank + "New prompt"
- [ ] Expandable writing-history rows
- [ ] Sort/filter in the URL on Opportunities
- [ ] Free-tier nudge in `RecommendationsWidget`
- [ ] Recovery actions on all terminal "no result" states
- [ ] Remove or relabel the discarded onboarding fields

## Accessibility
- [ ] `<main id="main-content">` in both layouts
- [ ] Focus trap + Escape on all dialogs
- [ ] Keyboard navigation for Reading questions
- [ ] `aria-live` on streaming regions
- [ ] Contrast audit

## Production
- [ ] **Add frontend to CI** (vitest + tsc + build)
- [ ] ESLint config + `lint`/`typecheck` scripts
- [ ] Sentry in both error boundaries
- [ ] Gate `/design-system`
- [ ] `not-found.tsx` + route-level `loading.tsx`
- [ ] Repo hygiene + type consolidation + `chat-shell` split

---

# PHASE 14 — Missing backend support

Frontend work that **cannot** be completed as-is.

### 14.1 🔴 Reading exam result retrieval
- **Missing:** `GET /api/exam/sessions/{id}/result` returning Reading's `per_question_result` + `section_breakdown`. The generic result route exists but returns `raw_score`/`band_score` only; the full breakdown exists **only** as the response body of `PUT /api/exam/reading/{id}/submit`.
- **Consequence:** results are held in `sessionStorage` and are permanently lost when the tab closes. A completed, graded exam becomes unviewable. Blocks `/exam/history` from linking to Reading detail.
- **Owner:** Exam service — persist the reading grading payload and expose it.

### 14.2 🟠 Server-side checklist list
- **Missing:** `GET /api/checklists` returning the user's checklists with programme metadata and progress.
- **Consequence:** `/checklists` is backed by `localStorage`. New device or cleared storage ⇒ checklists vanish from the UI while persisting server-side. Directly contradicts the page's own promise.
- **Owner:** RAG service (`checklists.py` already has per-programme routes).

### 14.3 🟠 Listening audio delivery
- **Missing:** an Exam-service endpoint returning a section's S3 pre-signed URL. Documented as a `TODO(GOA-059)` at `services/gateway/server.go:258`: presigned URLs are minted inside `create_listening_session`, returned only in `GET /exam/listening/start`, never persisted; the Gateway holds no S3 credentials.
- **Consequence:** the Listening exam cannot be built. **Already cut** in SCOPE-REDUCTION §1 — record as a documented gap, not a task.

### 14.4 🟡 CV review history
- **Missing:** a listable store of past CV review results. Only `GET /cv/latest` (most recent upload) and a content-keyed cache exist.
- **Consequence:** `/cv-review`'s honest "Review history isn't available yet" empty state.

### 14.5 🟡 Essay detail
- **Missing:** `GET /api/writing/essays/{id}` returning the full stored evaluation. `GET /api/writing/essays` returns summaries only (`id`, date, status, band, excerpt).
- **Consequence:** Writing History rows cannot expand or link to a detail view. Blocks task 5.5.

### 14.6 🟡 Onboarding profile fields
- **Missing columns in `UpdateProfileDto`:** `university`, `graduationYear`, `targetDegree`, `targetMajor`, `targetIntake`, target IELTS score.
- **Consequence:** the wizard collects six values and discards them (documented in `buildProfilePayload`).

### 14.7 🟡 Speaking session audio
- **Missing:** stored audio (or a presigned URL) per speaking session.
- **Consequence:** you can read your transcript but never hear your own take — the single most useful thing for speaking practice.

### 14.8 🟢 Resend verification email
- **Missing:** `POST /auth/resend-verification`. Currently an unverified user with a lost email is stuck.

### 14.9 ⛔ Subscription upgrade
- **Missing:** everything. **No Stripe code exists anywhere in `services/`** (verified). No checkout, no webhook, no tier-change endpoint. The Gateway reads a tier and gates on it; nothing can change it from the product.
- **Consequence:** the paid tier is unpurchasable. **Cut by SCOPE-REDUCTION §1 #3** — the agreed substitute is a tier flag flipped administratively. The frontend should therefore ship an `/upgrade` page that *explains* the tier and requests it, not a checkout.

---

# PHASE 15 — Demo readiness

| Dimension | Score | Reasoning |
|---|---|---|
| UI completeness | **8.5** | 26 routes, real design system, consistent states, no placeholder content |
| Backend integration | **7.5** | 30/44 fully consumed; 3 finished features unwired |
| UX | **8.0** | Genuinely thoughtful copy and error taxonomy; upgrade path dead-ends |
| Reliability | **5.5** | Exam data loss + WS silent hang are both live-demo failure modes |
| Accessibility | **6.5** | Good primitives; broken skip link, untrapped dialogs |
| Performance | **7.5** | Server components on marketing, font strategy considered, dedupe; no caching |
| **Overall** | **7.4 / 10** | |

This is comfortably above the demo-readiness plan's 5.4 baseline and close to its 8.2 Phase-1 target.

### Must complete before demo day (~2 days)

1. **Reading answer persistence + `beforeunload`** (1.1, 1.2) — a stray refresh mid-demo ends the demo
2. **Speaking WS close-code handling + `evaluating` timeout** (4.2) — a dropped socket = frozen screen on stage
3. **Sidebar plan badge bound to real tier** (2.1) — visible in every screenshot
4. **`/upgrade` page** (2.2) — "what happens when I click Upgrade?" is the first question an examiner asks
5. **Notifications page + bell** (3.1) — turns a whole service from invisible to demoable in half a day
6. **`/exam/history`** (3.2) — makes the exam story complete
7. **Chat stop button** (4.4) — 30 minutes, visibly professional
8. **Exam mobile block styled** (1.6) — someone *will* open it on a phone

### Explicitly say in the demo, don't build
- Listening & Speaking *exam* modes: cut, and Listening is backend-blocked (§14.3)
- Stripe: cut; tier is administrative
- Reading results are session-scoped pending an Exam-service endpoint (§14.1)

---

# PHASE 16 — Production readiness

**Score: 6.2 / 10 — not production ready.**

### Hard blockers
1. **No token refresh** — every session dies at access-token expiry with no recovery
2. **Exam data loss** (E1) — unacceptable for a paid product
3. **Exam results unrecoverable** (E2) — users pay for scores they cannot revisit
4. **Frontend absent from CI** — 35 test files never run; nothing prevents a broken deploy
5. **No error reporting** — production failures are invisible
6. **No account deletion / data export UI** — GDPR-relevant, endpoints already exist
7. **Speaking WS unreliable** — silent hangs with no recovery
8. **Upgrade path non-functional** — a paid tier that cannot be bought

### Also required
9. ESLint + enforced typecheck · 10. `/design-system` publicly reachable · 11. No `not-found.tsx` · 12. Checklists device-local · 13. No caching layer (every navigation refetches) · 14. Hardcoded fallback identity · 15. No rate-limit UX outside Opportunities · 16. No offline/network-loss handling

---

# PHASE 17 — Final execution plan

Organised by **dependency**, not by page.

```
        ┌─────────────────────────────────────────────┐
        │ TRACK A — FOUNDATIONS (unblocks everything) │
        └─────────────────────────────────────────────┘
A1  Add frontend to CI + ESLint + typecheck              [M]  ← do first
A2  Auth interceptor (401 → refresh → replay)            [M]  ← every fetch depends on it
A3  Toast primitive + provider                           [M]  ← 8 later tasks consume it
A4  <main id="main-content"> in both layouts             [XS] ← unblocks all a11y work
                     │
     ┌───────────────┼────────────────┬──────────────────┐
     ▼               ▼                ▼                  ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌───────────────┐
│ B. EXAM  │  │ C. TIER    │  │ D. CONNECT   │  │ E. REALTIME   │
│ INTEGRITY│  │ CORRECTNESS│  │ THE BACKENDS │  │ RESILIENCE    │
│ ★CRITICAL│  │            │  │              │  │               │
│  PATH    │  │ C1 badge   │  │ D1 notifs    │  │ E1 WS retry   │
│ B1 persist│ │ C2 /upgrade│  │ D2 exam hist │  │ E2 close codes│
│ B2 unload│  │ C3 isPaid  │  │ D3 weak-areas│  │ E3 chat stop  │
│ B3 errors│  │ C4 kill    │  │ D4 /settings │  │ E4 abort SSE  │
│ B4 mobile│  │    user-lina│ │ D5 pagination│  │ E5 timeouts   │
└──────────┘  └────────────┘  └──────────────┘  └───────────────┘
     │               │                │                  │
     └───────────────┴────────┬───────┴──────────────────┘
                              ▼
              ┌───────────────────────────────┐
              │ F. POLISH (needs A3 toasts)   │
              │ modals · prompts · URL state  │
              │ history rows · empty states   │
              └───────────────────────────────┘
                              ▼
              ┌───────────────────────────────┐
              │ G. HARDENING                  │
              │ Sentry · not-found · refactor │
              └───────────────────────────────┘
```

### Critical path
**A1 → A2 → B (exam integrity) → E (realtime) → C2 (/upgrade).**
Everything else parallelises. B and E are the two tracks that decide whether a live demo survives; C2 is the one that decides whether the product story is coherent.

### Sequencing rules
- **A1 before any code change.** Landing CI first means every subsequent task is verified. It is also the cheapest task with the largest blast radius.
- **A2 before D.** A settings/notifications page that 401s after an hour is worse than no page.
- **A3 before F.** Building toasts once beats eight inline alerts you then rip out.
- **A4 before Milestone 6.** One line fixes 24 routes.
- **B and E can run in parallel** — different files, no overlap.
- **C2 (/upgrade) before C1 (badge)** — otherwise the corrected badge points at a dead link.

### Estimate

| Track | Effort | Cumulative |
|---|---|---|
| A — Foundations | 1.0 day | 1.0 |
| B — Exam integrity | 1.0 day | 2.0 |
| C — Tier correctness | 1.0 day | 3.0 |
| D — Connect backends | 1.5 days | 4.5 |
| E — Realtime resilience | 1.0 day | 5.5 |
| F — Polish | 1.0 day | 6.5 |
| G — Hardening | 1.0 day | 7.5 |
| A11y (Milestone 6) | 0.5 day | 8.0 |

- **Demo-solid (A + B + E + C1/C2 + D1/D2):** **4.5–5 days**
- **Feature-complete against the current backend (A–F):** **6.5–7 days**
- **Production-ready (all + backend gaps §14.1, §14.2, §14.5):** **~11 days**, of which ~3 are backend

### Highest value per hour

1. **`<main id="main-content">`** — XS, fixes a11y on 24 routes
2. **Sidebar tier badge** — XS, most visible bug in the product
3. **Chat stop button** — S, machinery already exists
4. **Reading answer persistence** — S, prevents catastrophic data loss
5. **Weak-areas wiring** — S, replaces an approximation with the real endpoint
6. **Writing history pagination** — S, the API already accepts the arguments
7. **Frontend in CI** — M, protects everything above it forever

---

## Closing note

The instinct behind "finish the frontend" is understandable, but the evidence does not support it. **26 of 29 intended routes exist and work.** What is left is (a) three pages over finished backends, (b) two data-durability bugs in the exam, (c) a realtime layer with no failure handling, and (d) a paid tier whose upgrade button goes nowhere. That is a focused ~5-day punch list, not a build-out — and the first day of it should be spent putting the frontend into CI so the other four are verified rather than hoped for.

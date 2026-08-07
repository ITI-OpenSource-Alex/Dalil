# Phase 2 — Nice Improvements

## Objective

Close the remaining rough edges that raise polish and reliability beyond the
Phase 1 baseline, without attempting anything that risks the flows Phase 1
just stabilized. Every sub-task below is independently schedulable and
individually low-effort; they are bundled into one document because none of
them is large enough to warrant its own file, per the ROI-ordered structure
of the overall plan.

## Background

The Demo Readiness Review identified a further set of issues that raise
demo quality but are not launch-blocking: a broken password-reset endpoint,
empty/slow screens caused by missing seed data and cold caches, phantom API
calls that 404 silently, disabled route protection, missing input caps, an
unbuilt Writing-exam word counter, and cosmetic (hardcoded) dashboard data.
None of these currently cause a hard failure on the primary demo path the
way the Phase 1 items did — they are refinements, not blockers.

## Why This Matters

Phase 1 gets the demo to a working, honest state. Phase 2 is what takes it
from "works" to "every reachable corner of the app is polished" — closing
404s, dead CTAs, and console errors that a reviewer poking around off-script
might stumble into, and fixing the one remaining screen (forgot password)
that fully errors today.

## Scope

**In scope:** the eight sub-tasks below, each scoped narrowly to its own
files.

**Out of scope:** anything requiring new backend endpoints, new database
tables, or cross-service work beyond a single seed/config change. Any task
that grew into that category during investigation was moved to Phase 3
instead (see that document).

## Sub-Tasks

Each sub-task below follows the same structure as the numbered Phase 1
documents, condensed. Status is tracked per sub-task in the table at the
end of this file.

---

### 2.1 — Fix the Forgot Password Endpoint

**Why it matters:** `ResetPasswordForm.tsx` posts `{email}` to
`/auth/reset-password`, which the gateway proxies to the user service's
reset handler — but that handler expects `{token, newPassword}`
(`ResetPasswordDto`). The correct target for an email-only request is
`/auth/forgot-password`. As a result, the form **always** fails with a 400
and displays "Something went wrong." This screen is linked directly from
the login page — a plausible click during any live Q&A.

**Files expected to change:**
```
services/frontend/components/auth/ResetPasswordForm.tsx
services/frontend/app/reset-password/page.tsx
services/frontend/components/auth/LoginForm.tsx
```

**Implementation strategy:** Point the form's POST at `/auth/forgot-password`
instead. The gateway route already exists and proxies correctly to the user
service, which rate-limits via `ForgotPasswordRateLimitGuard` and logs a
simulated SQS email (`[SQS Simulation] Send email to … with link: …`) — so
the flow completes successfully server-side even without a real mail
provider configured. The existing "Check your inbox" success state is
already correct and already satisfies the no-account-enumeration
requirement (it renders identically regardless of whether the email is
registered) — keep it as-is.

Naming is left slightly inconsistent by this fix (the route is
`/reset-password` but the screen requests a reset *link*) — a full rename to
`/forgot-password` would be the more correct long-term fix, but it also
touches the login page's link and the user service's emailed link format.
**For this task, fix only the endpoint target; do not rename the route** —
note the rename as Phase 3 follow-up rather than risking the emailed-link
contract under demo time pressure. The token-consuming screen that would
let someone actually complete a reset (accept `?token=`, collect a new
password) does not exist and is not built here — the demo only needs the
request screen to succeed without erroring, not a completable reset flow
end to end.

**Edge cases:** verify the success state behaves identically for both a
registered and an unregistered email address (no account enumeration).

**Acceptance criteria:**
- Submitting the form returns a 2xx response and renders the "Check your
  inbox" success state.
- The success state is identical regardless of whether the email is
  registered.
- The user service logs the simulated reset email in its output.

**Verification steps:**
1. From `/login`, click "Forgot password?".
2. Submit a registered email; confirm the success state and the
   `[SQS Simulation]` log line in the user service's output.
3. Submit an unregistered email; confirm an identical success state with no
   error.

**Dependencies:** None.

**Estimated effort:** 15 minutes.

**Risk:** Very Low.

**Status:** Not Started

---

### 2.2 — Warm Caches and Seed History Data

**Why it matters:** Two demo screens are empty or slow on first contact. The
speaking band-trend chart on `/speaking/history` has nothing to plot until
sessions exist, so that screen — one of the strongest in the demo — opens on
an empty state. And the first `GET /api/checklists/:programId` call
**triggers LLM generation**, which can take 10–30 seconds; hitting that cold
path live would stall the checklist demo segment for an uncomfortable
amount of time.

**Files expected to change:**
```
docs/dorgham-context/DEMO_RUNBOOK.md
services/speaking/  (a seed file, path per that service's existing migration convention)
```

**Implementation strategy:** For speaking history, prefer recording 4–6 real
sessions on demo-prep morning over hand-inserting rows — it takes about 15
minutes, produces data that's guaranteed to match exactly what the detail
view expects, and doubles as a smoke test of the entire speaking pipeline
(WebSocket, transcription, TTS, evaluation) shortly before presenting. Fall
back to direct database seeding, with an ascending band progression (e.g.
5.5, 6.0, 6.0, 6.5, 6.5, 7.0) dated across recent weeks, only if time is
short — an ascending trend matters because it tells a story about the
product working; randomly scattered bands do not.

For the checklist, add an explicit runbook step: hit the checklist endpoint
for the exact program that will be clicked during the demo, before
presenting. `useChecklist` persists the generated checklist after its first
call, so a warmed program then renders instantly on the actual demo run.
Warm every program that might plausibly be clicked, not only the one
scripted.

Optionally, seed 4–6 chat turns against the demo `sessionId` (see
[04 — Real User Identity Wiring](04-real-user-identity.md) for how that id
is now derived) so `/chat` opens on a lived-in conversation instead of a
single greeting — the existing mount-time history loader already fetches
and renders this with no code change required, only rows. This is optional
and lower-value than the two items above.

Document, in the runbook, every Redis cache key that must be flushed after
any seeding pass: RAG's `match:{user_id}` key (see
[03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)), and
the gateway's subscription cache, which holds a TTL-bound verdict on the
demo user's tier — a user manually upgraded in the database directly may
still read as free-tier in the gateway until that cache entry expires.

**Edge cases:** if speaking sessions are recorded live on demo morning
rather than seeded directly, confirm they're recorded under the same demo
account whose identity was wired in
[04 — Real User Identity Wiring](04-real-user-identity.md), or the trend
chart will not show them.

**Acceptance criteria:**
- `/speaking/history` renders a trend chart with at least 4 points on an
  ascending curve, plus a populated session list.
- Clicking any seeded/recorded session opens a complete evaluation
  breakdown.
- The demo program's checklist renders in under 2 seconds on first load
  during the actual demo.
- The runbook lists every cache key requiring a flush after seeding.

**Verification steps:**
1. Open `/speaking/history` as the demo user; confirm the chart and list are
   populated.
2. Open a session's detail view; confirm the per-criterion breakdown
   renders; confirm the Share action mints a link that opens correctly in
   an incognito window.
3. Time the checklist page's load with a stopwatch after warming; confirm
   it is under 2 seconds.

**Dependencies:** Should follow
[03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md) and
[04 — Real User Identity Wiring](04-real-user-identity.md), since both the
checklist program and the speaking sessions need to be tied to the same
real demo account identity established there.

**Estimated effort:** 45 minutes.

**Risk:** Very Low.

**Status:** Not Started

---

### 2.3 — Remove Phantom Next.js API Route Calls

**Why it matters:** `/exam` sends a `PATCH` to `/api/profile` on every
Academic/General toggle, and `/exam/results` sends a `POST` to
`/api/profile/update-scores` after every result. **Neither route exists** —
only `/api/chat` and `/api/chat/sessions/[sessionId]/history` are defined
under `app/api/`. Both calls therefore 404. The `PATCH` call additionally
has no `.catch` at all, producing an unhandled promise rejection visible in
the browser console. A reviewer who opens devtools during the exam segment
will see both the 404s and the red rejection.

**Files expected to change:**
```
services/frontend/app/exam/page.tsx
services/frontend/app/exam/results/page.tsx
```

**Implementation strategy:** Remove both calls entirely rather than
attempting to make them work. Neither can succeed as currently written —
the user service exposes no profile-update endpoint at all, so even a
correctly-implemented Next.js BFF route would have nothing valid to proxy
to. Keep the Academic/General exam-type toggle as local component state; it
already correctly drives `createSession`, which is all the demo actually
needs from it. Delete the score-sync `POST` entirely — its result is
already silently discarded on one call site and unhandled on the other, so
nothing currently depends on it succeeding. Leave a short comment at each
removed call site naming the missing upstream endpoint, so the intent isn't
lost for whoever eventually builds real profile persistence.

If real persistence is wanted later, it requires a new user-service
endpoint, a new gateway route, and the RAG profile-replication path all
being exercised correctly — realistically several hours of cross-service
work. That is explicitly **not** demo-prep work and is deferred to Phase 3.

**Edge cases:** confirm removing the `await`-ed `POST` in
`app/exam/results/page.tsx` doesn't change the surrounding function's
control flow — it currently sits inside a `try` block ahead of a `finally`;
read the full block before removing rather than assuming it's safe to
delete in isolation.

**Acceptance criteria:**
- No request to `/api/profile` or `/api/profile/update-scores` is issued
  from any page.
- No unhandled promise rejection appears in the console during the exam
  flow.
- The Academic/General toggle still correctly determines the exam type of
  a newly created session.

**Verification steps:**
1. Open `/exam` with devtools Network and Console open; toggle
   Academic/General several times; confirm zero requests fire and the
   console stays clean.
2. Complete a full Reading exam through to results; confirm no 404s appear
   and the console remains clean throughout.

**Dependencies:** None.

**Estimated effort:** 30 minutes.

**Risk:** Low.

**Status:** Not Started

---

### 2.4 — Re-enable Route Protection

**Why it matters:** The authenticated-route guard in `middleware.ts` is
currently commented out. A logged-out visitor can load `/chat`, `/exam`, and
`/profile`, see the full application shell render, and then watch every
subsequent API call fail with 401 — which reads as the application being
broken rather than as an intentional access boundary. This is also a
documented platform non-functional requirement. Fixing it converts an
apparent bug into a visible, mentionable security feature.

**Files expected to change:**
```
services/frontend/middleware.ts
```

**Implementation strategy:** Uncomment the protected-route redirect logic.
The existing `matcher` configuration and the `isProtectedRoute` /
`isAuthRoute` predicate functions are already correct and already cover
`/chat`, `/profile`, `/speaking/history`, and `/checklist`.

Two things must be confirmed **before** enabling this, not after:

- **Cookie name match.** The middleware checks for a cookie named
  `access_token`. Confirm this matches exactly what the gateway's login
  handler actually sets. A mismatch here means *every* authenticated user
  gets redirected to `/login` regardless of a valid session — a total demo
  lockout. Verify this directly in browser devtools before enabling, not by
  reading the code and assuming.
- **`/exam` is intentionally left out of the current matcher.** Given the
  exam flow's centrality to the demo, the lower-risk choice is to **leave
  `/exam` out of the matcher for the demo** and treat adding it as a
  separate follow-up, rather than expanding protection scope on a route the
  demo cannot afford to have blocked by a subtle bug.

Do not attempt the Next.js-suggested `middleware` → `proxy` migration
(flagged as deprecated in Next 16 build output) as part of this task — that
is an unrelated, unnecessary risk to take on this week.

**Edge cases:** the middleware only checks for cookie *presence*, not
validity — an expired token still passes the middleware check and then
401s at the gateway on the first real request. This is acceptable for the
demo, provided [11 — Loading and Error State Polish](11-loading-error-states.md)
and [10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md)
are already in place to handle that downstream failure gracefully. Confirm
the public speaking share route (`/speaking/share/[token]`) is not
accidentally caught by the `/speaking/history` matcher pattern — it must
remain reachable with no session.

**Acceptance criteria:**
- An unauthenticated request to `/chat`, `/profile`, or `/checklist/*`
  redirects to `/login`.
- An authenticated user reaches all protected routes with no redirect.
- An authenticated user visiting `/login` or `/register` is redirected to
  `/chat` (existing behavior, must remain unchanged).
- `/speaking/share/[token]` remains publicly accessible with no session.
- Login followed by landing on `/chat` succeeds on the first attempt, twice
  consecutively, starting from a fully cleared cookie jar.

**Verification steps:**
1. Clear all cookies. Visit `/chat`; confirm redirect to `/login`.
2. Log in; confirm landing on `/chat` with a working session and no
   redirect loop.
3. While logged in, visit `/login`; confirm redirect to `/chat`.
4. In an incognito window with no session, open a valid speaking share
   link; confirm it renders correctly.
5. Repeat steps 1–2 a second time from a fully cleared state, to rule out a
   one-time fluke.

**Dependencies:** None functionally, but should be sequenced after
[04 — Real User Identity Wiring](04-real-user-identity.md) so that the login
→ chat path being verified here reflects the real identity flow, not the
placeholder one.

**Estimated effort:** 30 minutes, including careful verification.

**Risk:** **Medium — the highest-risk item in this document.** This is
exactly the category of change that works in local testing and then locks
the presenter out on demo day if the cookie-name assumption is wrong. Test
the full login → redirect → chat path immediately after enabling it, twice.
If anything about the cookie behavior is ambiguous, defer this task rather
than risk it — a slightly less-protected demo is recoverable; a locked-out
presenter mid-demo is not.

**Status:** Not Started

---

### 2.5 — Chat and Essay Input Caps and Counters

**Why it matters:** The platform spec caps chat input at 2000 characters
(prompt-injection and cost containment) and essay submissions at 5000
characters (already enforced server-side by the gateway's
`ValidateEssayTextLength(5000)` middleware). Neither cap is reflected in
the frontend UI today. A user who pastes a long essay would have it
silently rejected by the gateway with no client-side explanation of why.

**Files expected to change:**
```
services/frontend/components/chat/chat-input.tsx
services/frontend/components/chat/essay-composer.tsx
```

**Implementation strategy:** Add a `maxLength` constraint and a live
character counter beneath each textarea. Show the counter only once input
crosses roughly 75% of the cap, so it doesn't clutter the resting empty
state. Style it neutral by default, switching to an amber/warning color as
the limit is approached. Disable the send/submit action once the cap is
reached. Use exactly 2000 for the chat input and exactly 5000 for the essay
composer — matching the essay cap to the gateway's enforced value exactly;
a client-side cap looser than the server's would let a user submit
something the server then silently rejects, which is the same class of
problem this task exists to fix.

**Edge cases:** the chat input's existing auto-grow height effect
recalculates on every keystroke — confirm the counter's appearance and
disappearance doesn't introduce a layout shift or jitter in that
calculation.

**Acceptance criteria:**
- The chat input hard-caps at 2000 characters; the essay composer hard-caps
  at 5000.
- A counter appears once input crosses roughly 75% of the relevant cap and
  turns amber near the limit.
- The send/submit action is disabled once the cap is reached.
- No layout shift occurs when the counter appears or disappears.

**Verification steps:**
1. Attempt to paste 2100 characters into the chat input; confirm it
   truncates at 2000 and a counter is visible.
2. Attempt to paste 5100 characters into the essay composer; confirm the
   same behavior at 5000.
3. Confirm the chat input's auto-grow behavior is unaffected and nothing
   visibly jumps as the counter appears.

**Dependencies:** None.

**Estimated effort:** 30 minutes.

**Risk:** Very Low.

**Status:** Not Started

---

### 2.6 — Live Word Counter for the Writing Exam

**Why it matters:** The Writing exam in the current branch is two bare
textareas with no word counter, no tabs, and no time guidance. A word
counter is the single most immediately recognizable IELTS writing
affordance — without it, the screen simply doesn't read as an exam. The
fully polished version of this UI exists on branch
`fix/GOA-058-writing-exam-ui`, but merging that branch wholesale is
deliberately deferred to Phase 3 given its conflict risk with the current
branch's Reading exam integration (see that document for detail). This task
is the cheap, low-risk subset of that work that captures most of the
visible benefit on its own.

**Files expected to change:**
```
services/frontend/app/exam/shell/page.tsx
services/frontend/lib/writing-word-count.ts        (new)
```

**Implementation strategy:** Extract a small, standalone word-count helper
and render a live counter beneath each Writing task's textarea: colored
orange below the task's target word count, green at or above it (150 words
for Task 1, 250 for Task 2).

**The counting algorithm must match the server's exactly.**
`session_service.py` determines the actual word-count penalty using
`len(essay_text.split())`. The frontend equivalent is
`trim().split(/\s+/).filter(Boolean).length`. Do **not** use a regex
word-boundary count (e.g. `\b\w+\b` matching) — `GOA-058_remaining_work.md
§3.7` documents that three separate, disagreeing word-count
implementations already exist across the writing pipeline's services. A
fourth implementation that disagrees with the one actually driving the
server-side penalty decision would show the candidate a green (safe)
counter in the UI while the server silently applies a penalty — a worse
outcome than having no counter at all.

If an under-minimum warning is added alongside the counter, it **must be
parameterized by task number**, not hardcoded to one task's threshold.
`GOA-058_remaining_work.md §2.1` documents exactly this bug on the
reference branch: the warning text hardcodes Task 1's 150-word threshold
and displays it verbatim even when shown against Task 2's evaluation,
producing a message that is provably false for a candidate who wrote, say,
200 words on Task 2 (which is under Task 2's 250-word target but over the
150 the message claims). Do not reproduce that defect here.

Write the counting helper as a small, standalone module so that the
eventual Phase 3 merge of the full GOA-058 Writing exam UI can adopt or
cleanly replace it, rather than needing to be reconciled with an
inline implementation.

**Edge cases:** test the algorithm against empty input, whitespace-only
input, multiple consecutive spaces, newlines and tabs, and punctuation-only
tokens — these are the specific cases the reference branch's own unit tests
cover, and matching them confirms the two implementations genuinely agree.

**Acceptance criteria:**
- Each Writing task's textarea shows a live word count that updates on
  every keystroke.
- The counter's color switches from orange to green at exactly 150 words
  (Task 1) and 250 words (Task 2).
- The counting algorithm matches `len(text.split())` behavior for all
  tested edge-case inputs.
- Any under-minimum warning correctly names the threshold for **its own**
  task, never the other task's threshold.
- Unit tests cover the enumerated edge cases.

**Verification steps:**
1. Start a Writing exam session; type into the Task 1 textarea; confirm the
   count increments correctly per word as typed.
2. Cross 150 words in Task 1; confirm the counter switches from orange to
   green.
3. Type roughly 200 words into Task 2; confirm it remains orange (under its
   250-word target) and that any warning text correctly cites 250, not 150.
4. Run the test suite; confirm the new unit tests pass.

**Dependencies:** None blocking, though this task's output is explicitly
designed to be superseded cleanly by
[Phase 3's GOA-058 merge task](phase-3.md) — see that document.

**Estimated effort:** 40 minutes.

**Risk:** Low. Purely additive UI within one branch of the exam shell; does
not touch the Reading branch.

**Status:** Not Started

---

### 2.7 — Real Exam Dashboard Bands with an Honest Empty State

**Why it matters:** `/exam` currently displays hardcoded band scores
(`{Reading: "6.5", Listening: "6.5", Speaking: "6.0", Writing: "5.5"}`), a
static "Current overall 6 ↗ +0.5 this month" delta, and a static "GOA
suggests… your biggest score lever for TU Munich" banner. After the
presenter completes a real Reading exam live during the demo, this
dashboard will still display 6.5 regardless of the actual result achieved —
a discrepancy a reviewer who just watched the real score appear may well
notice and question.

**Files expected to change:**
```
services/frontend/app/exam/page.tsx
```

**Implementation strategy:** Source displayed bands from `useCurrentUser()`
(already a dependency of this codebase after
[04 — Real User Identity Wiring](04-real-user-identity.md)), which returns
`user.profile.ieltsScore` and related fields. Note explicitly that the
profile carries a single overall IELTS score, not per-skill sub-bands — so
per-skill cards cannot be fully and correctly populated from this data
source alone. Design the display around that real constraint rather than
inventing per-skill numbers that don't actually exist anywhere in the data
model.

Recommended treatment: show a real value where the profile actually
provides one, and a clean, neutral "—" with a "Not yet attempted" caption
where it does not. An honest empty state reads as a real, unfinished
product feature; a fabricated 6.5 reads as a mockup, which is strictly
worse.

Remove the "↗ +0.5 this month" delta entirely — there is no historical data
anywhere in the current data model to compute it from, and displaying it
implies tracking that doesn't exist. Either remove the "GOA suggests"
banner entirely, or reword it to something defensible that isn't tied to a
specific university the user never actually selected.

**Do not** attempt a full exam-history integration as part of this task —
the `/exam-history` endpoint and a proper Exam Progress tab are
substantially larger work, tracked in the Phase 3 backlog.

**Edge cases:** confirm the empty-state treatment for a brand-new account
(no profile data at all) is visually clean and doesn't leave the card grid
looking broken or unfinished in its own right.

**Acceptance criteria:**
- No hardcoded band constant remains anywhere in the file.
- Skills with no recorded band show a neutral empty indicator, never a
  fabricated number.
- The fabricated month-over-month delta is removed.
- The suggestion banner either is removed or contains no unfounded claim
  tied to data that doesn't exist.

**Verification steps:**
1. Open `/exam` as a brand-new account with no exam history; confirm all
   four skill cards show honest empty indicators, not numbers.
2. Complete a real Reading exam; return to `/exam`; confirm the displayed
   state is consistent with (or honestly silent about) the actual result —
   never contradicting what the reviewer just watched happen.

**Dependencies:** Requires
[04 — Real User Identity Wiring](04-real-user-identity.md) to be in place,
since it depends on `useCurrentUser()` returning the real logged-in
account's profile data.

**Estimated effort:** 1 hour.

**Risk:** Low. Read-only display logic sourced from an already-existing,
already-verified hook.

**Status:** Not Started

---

### 2.8 — Minimal `/pricing` Route

**Why it matters:** Once
[05 — Landing Page Components](05-landing-page.md) delivers a real
`Pricing` component and section, both the navbar and that section want
somewhere real to send a "Subscribe" or pricing-related click. No
`/pricing` route currently exists, so any such CTA 404s. This task is only
worth doing after the landing-page task lands, at which point it is nearly
free — it's almost entirely composition of an already-built component.

**Files expected to change:**
```
services/frontend/app/pricing/page.tsx        (new)
services/frontend/components/landing/Navbar.tsx
services/frontend/components/ui/sidebar.tsx
```

**Implementation strategy:** Build a thin page composing the existing
`Navbar`, the `Pricing` component built in
[05 — Landing Page Components](05-landing-page.md), and `Footer`. The
"Subscribe" action should route logged-out visitors to `/register`; for
already-logged-in users, render a clearly-labeled "Billing coming soon"
state rather than a dead or misleading button. No Stripe integration, no
gateway billing routes — neither exists today and neither is in scope for
this task or this demo.

Once this route exists, the sidebar's currently-nonfunctional "Upgrade"
button (a bare `<button>` with no click handler at all) can finally point
somewhere real, closing one more dead interactive element in the
application.

**Edge cases:** none beyond what's already covered by the underlying
`Pricing` component's own edge cases (see
[05 — Landing Page Components](05-landing-page.md)).

**Acceptance criteria:**
- `/pricing` renders with the same navbar/footer chrome as the rest of the
  application.
- No Pricing-related call to action anywhere in the app (navbar, landing
  page, sidebar) results in a 404.
- The Subscribe action leads to a sensible destination and never dead-ends
  silently.

**Verification steps:**
1. Click "Pricing" in the navbar; confirm navigation to `/pricing`.
2. While logged out, click Subscribe; confirm navigation to `/register`.
3. While logged in, click the sidebar's Upgrade button; confirm navigation
   to `/pricing` and a clear "coming soon" billing state.

**Dependencies:** Requires
[05 — Landing Page Components](05-landing-page.md) to be complete first —
this task composes that document's `Pricing` component rather than building
a second one.

**Estimated effort:** 30 minutes.

**Risk:** Very Low.

**Status:** Not Started

---

## Phase 2 Summary Table

| # | Task | Effort | Risk | Status |
|---|---|---|---|---|
| 2.1 | Fix forgot-password endpoint | 15 min | Very Low | Not Started |
| 2.2 | Warm caches + seed history | 45 min | Very Low | Not Started |
| 2.3 | Remove phantom API routes | 30 min | Low | Not Started |
| 2.4 | Re-enable route protection | 30 min | **Medium** | Not Started |
| 2.5 | Input caps and counters | 30 min | Very Low | Not Started |
| 2.6 | Writing exam word counter | 40 min | Low | Not Started |
| 2.7 | Real exam dashboard bands | 1 h | Low | Not Started |
| 2.8 | Minimal `/pricing` route | 30 min | Very Low | Not Started |
| | **Total** | **≈ 4.5 h** | | |

## Overall Status

Not Started

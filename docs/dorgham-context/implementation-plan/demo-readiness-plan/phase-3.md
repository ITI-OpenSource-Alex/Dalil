# Phase 3 — Post-Demo Backlog

## Objective

Record every larger, higher-risk, or genuinely out-of-scope item identified
during the Demo Readiness Review, so the work is not lost, but explicitly
scheduled **after** the demo rather than competing with it for time or risk
budget.

## Background

The Demo Readiness Review surfaced a number of real gaps — some are large
features that were never in scope for a demo (billing, CV review,
notifications), some are backend-blocked (Listening exam, Speaking exam
simulation), and some are genuinely valuable but carry a regression risk to
Phase 1's stabilized flows that isn't worth taking on a compressed
timeline (merging the GOA-058 Writing exam UI branch). All of them are
listed here for completeness and future planning, not because any of them
is expected to happen before the demo.

## Why This Matters

Explicitly deferring this work — rather than silently dropping it or
letting it creep into Phase 1/2 scope under time pressure — is itself a risk
control. Every item below was deliberately excluded from the demo-prep
phases for a stated reason; keeping that reasoning attached to the backlog
item prevents it from being re-litigated from scratch later, and prevents
someone from picking one up under demo-week time pressure without
understanding why it was set aside.

## Scope

**In scope:** documenting each deferred item with enough context (why it's
deferred, what it would take, what it depends on) that it can be picked up
independently later, without needing to re-derive the reasoning from the
original review.

**Out of scope:** implementing, scoping in detail, or scheduling any of
these items against a specific date. This document is a backlog record, not
an implementation plan for its own contents.

## Backlog Items

---

### 3.1 — Merge the Writing Exam UI from `fix/GOA-058-writing-exam-ui`

**What it is:** That branch contains a complete Writing exam
implementation — `WritingExam.tsx`, `WritingTaskPanel.tsx`,
`StimulusPanel.tsx`, `TaskResultCard.tsx`, `CombinedWritingResults.tsx`,
`lib/writing-exam.ts` — with tabbed Task 1/Task 2 panels, the live word
counter with orange/green states, recommended-time indicators, a collapsed
Task 1 result card that leaves Task 2 fully editable, and the explicit
33%/67% weighted band formula. Per `GOA-058_remaining_work.md`, it was
verified end-to-end against the live stack, including through the real
gateway. This is a finished feature currently sitting unmerged and
undemoable.

**Why it's deferred:** Both the current branch and
`fix/GOA-058-writing-exam-ui` have independently modified
`app/exam/shell/page.tsx` and `app/exam/results/page.tsx` — the current
branch added the Reading exam integration to exactly those same files. A
conflicted merge attempted under demo-week time pressure risks breaking the
Reading exam, which is the single strongest asset in the entire
application. The payoff (a fully polished Writing exam) is real, but not
worth that specific risk on a compressed timeline. Note that
[Phase 2, item 2.6](phase-2.md) already captures the cheap, low-risk subset
of this branch's value (the word counter alone) without touching either of
the two conflicted files.

**What it would take:** Perform the merge on a throwaway branch first.
Resolve conflicts so that the current branch's Reading exam shell
integration is preserved verbatim, not merely "resolved" in a way that
happens to compile. Run the full Reading exam flow as a regression gate
*before* even looking at whether the Writing side works. Fix the
Task 2 under-minimum warning-text bug documented in
`GOA-058_remaining_work.md §2.1` as part of the merge, not after. Do not
attempt the Academic Task 1 stimulus chart image — that is separately
documented as blocked on multi-sprint backend and infrastructure work (see
item 3.10 below) and is out of scope even for this merge.

**Acceptance criteria (for whenever this is picked up):**
- The Reading exam flow is bit-for-bit unchanged in behavior after the
  merge.
- The Writing exam renders tabs, per-task word counters, and time
  indicators.
- Combined results show the explicit weighted formula, matching the
  specification's example string exactly.
- The under-minimum warning cites the correct threshold for whichever task
  it's displayed against.
- `next build` passes cleanly.

**Estimated effort:** 2–3 hours, including conflict resolution and
re-verification.

**Risk:** **High.** The primary risk is regressing the Reading exam via
merge conflict resolution in the two shared files.

---

### 3.2 — Onboarding Persistence

**What it is:** The 4-step onboarding wizard currently persists nothing —
`handleFinish` simply routes to `/chat` with no API call, and the CV
upload step is entirely simulated with a fake `setInterval` progress bar.

**Why it's deferred:** Genuinely blocked on a missing backend endpoint —
the user service exposes no `PUT /users/:id/profile` or equivalent, only
`POST /`, `GET /internal`, `GET /:id`, `GET /:id/subscription`. Building
this requires new work across at least the user service and the frontend,
and arguably the RAG profile-replication path as well.

**Estimated effort:** Half day or more.

---

### 3.3 — Profile Editing, Auto-Save, and Tabs

**What it is:** `/profile` today is read-only. The spec calls for an
editable form with auto-save-on-blur, a CV upload section, an Opportunities
tab, and an Exam Progress tab.

**Why it's deferred:** Blocked on the same missing profile-update backend
endpoint as item 3.2. A read-only profile page is adequate for the demo's
needs once it's actually reachable (see
[06 — Sidebar Navigation Cleanup](06-sidebar-navigation.md)).

**Estimated effort:** Full day.

---

### 3.4 — Exam Progress Tab and `/exam-history` Integration

**What it is:** A proper Exam Progress tab on `/profile` showing a
per-skill score trend chart, a weak-areas panel, and a recent-exams list,
per the specification.

**Why it's deferred:** Requires history endpoints and per-skill band
storage that don't currently exist in a form the frontend can consume; a
substantially larger effort than the honest-empty-state fix already applied
to the exam dashboard in
[Phase 2, item 2.7](phase-2.md).

**Estimated effort:** Full day.

---

### 3.5 — Token-Consuming Reset-Password Screen

**What it is:** A screen that accepts a `?token=` query parameter, collects
a new password and confirmation, and calls `POST /auth/reset-password` with
`{token, newPassword}` — completing the password-reset flow that
[Phase 2, item 2.1](phase-2.md) only starts (the request-a-link screen).

**Why it's deferred:** The demo only needs the request screen to not error;
a fully completable reset flow isn't part of the demo script.

**Estimated effort:** 2 hours.

---

### 3.6 — Email Verification Page

**What it is:** A frontend page for `/verify-email/:token`, calling the
already-existing gateway endpoint `GET /auth/verify-email/:token` on mount
and showing a success/error state.

**Why it's deferred:** Not on the demo path at all; the gateway route
exists but nothing in the frontend currently uses it.

**Estimated effort:** 1 hour.

---

### 3.7 — CV Review Surface

**What it is:** A dedicated CV upload and review interface, streaming
section-by-section feedback (structure, ATS keywords, country-specific
conventions) per the specification.

**Why it's deferred:** The gateway and orchestration both already support
routing a CV review request (see `writing_client.py`'s CV-adjacent
handling and the orchestration `CV_REVIEW` intent), but no frontend surface
exists for it at all — this is a full feature build, not a fix.

**Estimated effort:** Full day or more.

---

### 3.8 — Upgrade Modal and Stripe Billing

**What it is:** The inline "Upgrade Prompt Modal" triggered by a gateway
403 `subscription_required` response, the `/pricing` page's real Stripe
Checkout integration, payment confirmation handling, and the Stripe
Customer Portal link for managing an existing subscription.

**Why it's deferred:** Explicitly out of demo scope per the original Demo
Readiness Review's framing — the demo does not need real billing, only an
honest "coming soon" state (delivered in
[Phase 2, item 2.8](phase-2.md)).

**Estimated effort:** Multi-day.

---

### 3.9 — In-App Notifications UI

**What it is:** A notification badge and panel surfacing scholarship/program
match notifications, per the specification.

**Why it's deferred:** The gateway already exposes `GET /api/notifications`,
but nothing in the frontend consumes it. Not on the demo path.

**Estimated effort:** Half day.

---

### 3.10 — Listening Exam

**What it is:** A full Listening exam implementation: a custom HTML5 audio
player with seeking disabled, sequential 4-section progression, a scratch
pad, a 30-second inter-section silence countdown, and a 10-minute
post-audio answer-transfer period.

**Why it's deferred:** Genuinely blocked on backend/infrastructure work
that doesn't exist yet — documented directly in
`services/gateway/server.go` near the exam route registration: the exam
service exposes no endpoint that returns a pre-signed S3 URL for a
session's audio, and the gateway holds no S3 credentials of its own to
generate one independently. This is explicitly named as blocked on work
owned by a different team.

For the demo, this gap is handled honestly rather than hidden — see
[08 — Exam Placeholder Replacement](08-exam-placeholders.md), which marks
this skill as "coming soon" on the dashboard instead of exposing the
placeholder workspace.

**Estimated effort:** Multi-sprint.

---

### 3.11 — Speaking Exam (In-Exam, 3-Part Structure)

**What it is:** The full strict-structure IELTS Speaking exam simulation
inside the exam shell: Part 1 interview questions, Part 2 cue card with a
60-second prep timer, Part 3 discussion, neutral confirmation screens
between parts, and a full-screen evaluating overlay after submission.

**Why it's deferred:** Substantial, multi-sprint UI and orchestration work.
The standalone Speaking Practice flow already reachable from `/chat`
already demonstrates the platform's core speaking capability (waveform,
live transcript, per-criterion band evaluation) convincingly on its own,
without needing the full in-exam structure built out for this demo. Also
handled via the "coming soon" treatment in
[08 — Exam Placeholder Replacement](08-exam-placeholders.md).

**Estimated effort:** Multi-sprint.

---

### 3.12 — Per-Agent Timeout Retry for Writing Evaluation

**What it is:** `GOA-058_remaining_work.md §3.3` documents that a single
evaluator-agent `APITimeoutError` currently fails an entire 4-agent writing
evaluation with no automatic retry, even though the other 3 agents may have
already succeeded.

**Why it's deferred:** A real backend reliability gap, but with low
probability of manifesting during a single, short live demo submission; not
worth the backend engineering time this week.

**Estimated effort:** 2 hours.

---

### 3.13 — Duplicate-Submit Race on Writing Exam Timer Expiry

**What it is:** `GOA-058_remaining_work.md §3.4` documents a race where a
manual "Submit" click in flight at the exact moment the exam timer expires
can trigger a second, concurrent submission for the same task.

**Why it's deferred:** The backend UPSERTs on `(session_id, task_number)`,
so the race is wasteful (duplicate LLM cost) but harmless to the outcome
the candidate sees. Low priority given that harmlessness.

**Estimated effort:** 1 hour.

---

### 3.14 — Word-Count Algorithm Unification Across Services

**What it is:** `GOA-058_remaining_work.md §3.7` documents that the writing
service, the exam service, and the frontend each implement word-counting
slightly differently, and that this divergence has already caused at least
one production-impacting bug elsewhere in the pipeline.

**Why it's deferred:** Currently low-impact — the specific divergent value
populates an informational field the frontend doesn't display or act on.
Pure technical debt with no live symptom today, but flagged because this
exact class of silent divergence has caused real bugs before in this
codebase and is worth cleaning up eventually.

**Estimated effort:** 2 hours.

---

### 3.15 — `middleware` → `proxy` Migration

**What it is:** Next.js 16's build output warns that the `middleware` file
convention (used by `services/frontend/middleware.ts`, central to
[Phase 2, item 2.4](phase-2.md)'s route-protection fix) is deprecated in
favor of a new `proxy` convention.

**Why it's deferred:** A deprecation warning only, with no functional
impact today. Migrating framework conventions during demo-prep week is an
unnecessary risk with no demo-facing benefit; revisit after the demo, once
there's time to verify the migration doesn't change auth-redirect behavior.

**Estimated effort:** 1 hour.

---

## Phase 3 Summary Table

| # | Item | Effort | Why Deferred |
|---|---|---|---|
| 3.1 | Merge GOA-058 Writing exam UI | 2–3 h | High regression risk to Reading exam |
| 3.2 | Onboarding persistence | Half day+ | Blocked on missing backend endpoint |
| 3.3 | Profile editing/auto-save/tabs | Full day | Same backend blocker as 3.2 |
| 3.4 | Exam Progress tab + history | Full day | Needs new history endpoints |
| 3.5 | Token-consuming reset screen | 2 h | Not needed for demo script |
| 3.6 | Email verification page | 1 h | Not on demo path |
| 3.7 | CV Review surface | Full day+ | Full feature build, no frontend exists |
| 3.8 | Upgrade modal + Stripe billing | Multi-day | Explicitly out of demo scope |
| 3.9 | In-app notifications UI | Half day | Not on demo path |
| 3.10 | Listening exam | Multi-sprint | Blocked on exam-service audio endpoint |
| 3.11 | Speaking exam (in-exam) | Multi-sprint | Standalone practice already demos capability |
| 3.12 | Per-agent timeout retry | 2 h | Low demo probability |
| 3.13 | Duplicate-submit race | 1 h | Harmless in outcome (UPSERT) |
| 3.14 | Word-count algorithm unification | 2 h | Pure tech debt, no live symptom |
| 3.15 | `middleware` → `proxy` migration | 1 h | Deprecation warning only, unnecessary risk now |

## Overall Status

Not Started (not scheduled against the demo date)

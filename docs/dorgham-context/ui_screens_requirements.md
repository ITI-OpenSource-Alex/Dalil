# Global Opportunity Assistant (GOA) — UI Screens & Requirements Specification

> A screen-by-screen catalogue of every user-facing interface in the Global Opportunity
> Assistant platform, with the **functional requirements** (what the screen must do) and
> **non-functional requirements** (how it must behave — performance, security,
> accessibility, reliability, constraints) for each.
>
> This document is concerned only with *what appears on each screen and what it must do* —
> not with visual or UX styling decisions.

---

## Table of Contents

**Public & Authentication**
1. [Landing Page](#1-landing-page)
2. [Register](#2-register)
3. [Login](#3-login)
4. [Forgot Password](#4-forgot-password)
5. [Reset Password](#5-reset-password)
6. [Email Verification](#6-email-verification)
7. [Onboarding Wizard](#7-onboarding-wizard)

**Core Application**
8. [Chat / Main Assistant](#8-chat--main-assistant)
9. [Opportunity Matches](#9-opportunity-matches)
10. [Opportunity / Program Detail Modal](#10-opportunity--program-detail-modal)
11. [Application Checklist](#11-application-checklist)
12. [User Profile Page](#12-user-profile-page)
13. [CV Review](#13-cv-review)
14. [Speaking Practice (Non-Exam)](#14-speaking-practice-non-exam)
15. [Speaking Session History](#15-speaking-session-history)
16. [Writing Practice (Non-Exam)](#16-writing-practice-non-exam)

**Subscription & Billing**
17. [Upgrade Prompt Modal](#17-upgrade-prompt-modal)
18. [Pricing Page](#18-pricing-page)
19. [Payment Confirmation](#19-payment-confirmation)
20. [Manage Subscription](#20-manage-subscription)

**IELTS Exam Preparation**
21. [Exam Prep Dashboard](#21-exam-prep-dashboard)
22. [Exam Shell (Shared)](#22-exam-shell-shared)
23. [Reading Exam](#23-reading-exam)
24. [Listening Exam](#24-listening-exam)
25. [Speaking Exam](#25-speaking-exam)
26. [Writing Exam](#26-writing-exam)
27. [Exam Results](#27-exam-results)
28. [Exam Progress / History](#28-exam-progress--history)

**Cross-Cutting**
29. [In-App Notifications](#29-in-app-notifications)

---

# Public & Authentication

## 1. Landing Page

**Route:** `/` · **Access:** Public (no authentication)

### Functional Requirements
- Display a hero section: headline, subheadline, and a primary **Get Started Free** call-to-action button.
- Display a **See how it works** / how-it-works section (4 steps with supporting icons).
- Display three feature cards: **Opportunity Matching**, **IELTS Preparation**, **CV Review**.
- Display a **Free vs Paid tier** comparison table.
- Display a footer with navigational links.
- Provide a path to **Register** and **Login**.
- No login wall — the entire page is browsable without an account.

### Non-Functional Requirements
- **Fully static** — makes zero API calls; served as a static Next.js bundle via CloudFront/S3.
- **SEO-ready:** meta title, meta description, and `og:image` defined.
- **Accessibility:** Lighthouse accessibility score > 90.
- Served behind WAF and Route 53; HTTPS-only (HTTP requests 301-redirect to HTTPS).

---

## 2. Register

**Route:** `/register` · **Access:** Public

### Functional Requirements
- Form fields: name, email, password.
- **Create Account** action submits `POST /api/auth/register`.
- On success: user account created with `subscriptionTier = free`; user redirected to the onboarding wizard.
- Validate email uniqueness (error surfaced if email already exists).
- Issue a signed session on success (JWT + refresh token).

### Non-Functional Requirements
- Passwords are **bcrypt-hashed** server-side; never stored in plaintext.
- JWT stored in an **httpOnly cookie** (never in localStorage); 1-hour expiry with refresh token.
- If an already-authenticated user visits, redirect to `/chat`.
- All form controls accessible (ARIA labels, keyboard navigation).

---

## 3. Login

**Route:** `/login` · **Access:** Public

### Functional Requirements
- Form fields: email + password.
- Submit `POST /api/auth/login`; on success redirect to `/chat`.
- **Forgot password** link to `/forgot-password`.
- Error states:
  - Invalid credentials.
  - Account not verified — show a **resend verification** link.

### Non-Functional Requirements
- Redirect already-authenticated users straight to `/chat`.
- Credentials transmitted over HTTPS only.
- Accessible form (ARIA, keyboard navigation).

---

## 4. Forgot Password

**Route:** `/forgot-password` · **Access:** Public

### Functional Requirements
- Single email input field.
- Submit `POST /api/auth/forgot-password`.
- Display a generic success message **regardless of whether the email exists**.

### Non-Functional Requirements
- **No account enumeration** — identical response whether or not the email is registered.

---

## 5. Reset Password

**Route:** `/reset-password?token=...` · **Access:** Public (token-gated)

### Functional Requirements
- Fields: new password + confirm password.
- Submit `POST /api/auth/reset-password` (with token).
- On success: redirect to `/login` with a success banner.

### Non-Functional Requirements
- Reset only valid with a legitimate, unexpired token.
- New password subject to the same hashing rules as registration.

---

## 6. Email Verification

**Route:** `/verify-email/:token` · **Access:** Public (token-gated)

### Functional Requirements
- On mount, call `GET /api/auth/verify-email/:token`.
- Show a success or error state based on the result.
- On success: auto-redirect to `/chat` after 3 seconds.

### Non-Functional Requirements
- Graceful, friendly error state for invalid/expired tokens (no raw errors).

---

## 7. Onboarding Wizard

**Route:** `/onboarding` · **Access:** Authenticated · 4 steps

### Functional Requirements
- A progress bar at the top reflecting current step.
- Each step validates before allowing progression.
- **Step 1 — Academic background:** degree level (Bachelor / Master / None), field of study, GPA (numeric), ECTS credits completed, graduation year.
- **Step 2 — Language:** IELTS overall band (if taken) + individual skill bands (Reading / Listening / Speaking / Writing); or a *"Planning to take IELTS"* option.
- **Step 3 — Targets:** target countries (multi-select: UK, Germany, Italy, Canada, etc.), opportunity type (Masters study / Work / Both), field of interest.
- **Step 4 — CV upload (optional):** drag-and-drop zone for PDF/Word; shows upload progress and a **"Processing…"** state while extraction runs; **Skip** button available.
- Each step persists via `PUT /api/users/:id/profile`.
- On completion: redirect to `/chat`.

### Non-Functional Requirements
- Wizard is **optional but unlocks personalised matching immediately**.
- Wizard state held in **sessionStorage** across steps (survives accidental navigation).
- CV upload processed **asynchronously** — the user proceeds to the dashboard without waiting for extraction (CVUploaded event → Lambda).
- Profile updates publish a `UserUpdated` event consumed downstream for scoring (eventual consistency acceptable).

---

# Core Application

## 8. Chat / Main Assistant

**Route:** `/chat` · **Access:** Authenticated · Primary interface

### Functional Requirements
- Conversational chat interface; messages **stream token-by-token** (SSE) as the LLM generates them.
- A typing indicator while awaiting a response.
- Expandable textarea for free-text input (and for writing-practice essays — plain text only).
- Render **opportunity result cards** inline: confidence score bar, program name, university, country, deadline, and a **View requirements** button.
- Render **RAG answers** with cited sources listed below the answer.
- On first load: implicitly run an opportunity search and present the top 5 matches alongside a welcome message.
- Support the full set of conversational intents: Q&A, opportunity search, CV review, speaking practice, writing practice, exam-prep advice.
- Trigger the **Upgrade Prompt Modal** (inline) when a free user requests a paid feature.
- After a successful upgrade, show a confirmation banner (`/chat?upgraded=true`).
- Friendly error states for service unavailability (never raw errors).

### Non-Functional Requirements
- **Free-tier rate limit:** 20 RAG queries/hour (enforced at gateway; 21st request blocked).
- **Performance:** first-load matches returned in under 3 seconds; chat P95 latency < 5s.
- Personalised responses use the user's *real* exam data when available (overrides self-reported scores).
- Conversation context persists across sessions (long-term memory); user can wipe stored facts via `DELETE /api/sessions/memory`.
- All AI input sanitised against prompt injection; chat input capped at **2000 characters**.
- Answers grounded only in retrieved context; low-confidence retrieval returns an honest "insufficient data" response rather than a hallucination.

---

## 9. Opportunity Matches

**Surface:** `/chat` results & `/profile` → Opportunities tab · **Access:** Authenticated (free)

### Functional Requirements
- Display a ranked list of matched programs (top 10 on profile page; top 5 on first chat load).
- Each card shows: confidence score (colour-coded — green ≥ 80, amber 60–79, red < 60), program name, university, country, deadline, **View requirements** button.
- **Blocked programs** are shown (not hidden) with the specific failed eligibility gate, e.g. *"Your ECTS credits (150) are below the minimum required (180)"*, plus a **"Can I fix this?"** flag.
- Clicking a program opens the [Program Detail Modal](#10-opportunity--program-detail-modal).
- A **Get Checklist** action per opportunity card.

### Non-Functional Requirements
- Backed by a 3-stage scoring pipeline (hard gates → weighted soft scoring → LLM boost).
- Results should remain responsive even with the full program database scored.
- Scoring uses the locally-cached profile snapshot (eventual consistency acceptable).

---

## 10. Opportunity / Program Detail Modal

**Surface:** Modal over Matches / Profile · **Access:** Authenticated

### Functional Requirements
- Show full program requirements.
- Show a **gap report** comparing the user's profile to the requirements.
- Provide an **Apply** button.
- Provide an entry to generate the [Application Checklist](#11-application-checklist).

### Non-Functional Requirements
- Implemented as an accessible dialog (focus trap, keyboard dismiss, ARIA).

---

## 11. Application Checklist

**Surface:** Opportunity card → **Get Checklist** · **Access:** Authenticated (free flagship feature)

### Functional Requirements
- Generate a personalised checklist via `GET /api/opportunities/:programId/checklist?userId=:id`.
- Items grouped by phase: **Language Prep → Documents → Application → Post-acceptance**.
- Each item shows: title, description, estimated days, completion checkbox, blocked state, resource links.
- **Blocked items** visually distinguished (greyed out + lock icon) with the blocking reason.
- Checkbox state persisted to the database (`PUT /api/checklists/:id`).
- Calculate and display an estimated completion date (today + sum of remaining item days).
- **Export as PDF** button (browser print API).

### Non-Functional Requirements
- Available on the **free tier** (CV review, speaking, writing remain paid-only).
- Free users may generate checklists for **up to 3 programs**.
- Checkbox state survives page refresh.

---

## 12. User Profile Page

**Route:** `/profile` · **Access:** Authenticated · Tabs: Profile · Opportunities · Exam Progress

### Functional Requirements
- **Profile form:** GPA (0–4.0 or 0–100), IELTS overall + sub-scores, ECTS credits, degree-level dropdown, target countries (multi-select), field of study.
- Profile form **auto-saves on blur** (no explicit save button).
- **CV upload section:** drag-and-drop, with processing status (uploading → extracting → ready); PDF only.
- **Opportunities tab:** see [Opportunity Matches](#9-opportunity-matches).
- **Exam Progress tab:** see [Exam Progress / History](#28-exam-progress--history).

### Non-Functional Requirements
- Optimistic UI for auto-save; values persist across refresh.
- All forms accessible (ARIA labels, keyboard navigation).
- Profile edits publish `UserUpdated` for downstream scoring.

---

## 13. CV Review

**Surface:** `/chat` upload / Profile CV section · **Access:** Authenticated (**Paid**)

### Functional Requirements
- Accept a CV via drag-and-drop or click-to-upload (PDF), or reuse a CV uploaded during onboarding (no re-upload).
- Accept target context (e.g. target country, target field) via chat.
- Stream the evaluation back section-by-section (SSE) covering: structure/formatting, skills gaps, ATS keyword optimisation, length, country-specific conventions.
- Each section displays a **score (0–100)**, specific issues found, and suggested rewrites.
- A **"Rewrite this section"** button per section that triggers a targeted improvement.
- Support follow-up requests (e.g. *"Rewrite my summary section"*).

### Non-Functional Requirements
- **Paid-tier only** — free users hit the [Upgrade Prompt Modal](#17-upgrade-prompt-modal) (403 `subscription_required`).
- Uploaded files stored in S3; text extraction asynchronous.
- Country-specific conventions retrieved via RAG (e.g. German Lebenslauf format).

---

## 14. Speaking Practice (Non-Exam)

**Surface:** `/chat` → **Start Speaking Practice** · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Start Speaking** button requests microphone permission (MediaRecorder API).
- Stream audio over WebSocket to the Speaking service.
- Display a **real-time waveform visualiser** while recording.
- Display a **live transcript** as the user speaks.
- On session end: display evaluation results with **per-criterion band scores** (Fluency, Lexical, Grammar, Pronunciation) and spoken feedback (TTS).
- Session state machine: idle → listening → transcribing → evaluating → done.

### Non-Functional Requirements
- **Paid-tier only.**
- **Latency target:** first TTS audio reaches the client in **under 3 seconds (P95)** from end of speaking; SLO violations logged.
- Audio streamed as PCM 16kHz mono; voice-activity detection triggers transcription after ~1.5s of silence.
- **Daily limit:** 30 minutes speaking/day per user.

---

## 15. Speaking Session History

**Route:** `/speaking/history` · **Access:** Authenticated (**Paid**)

### Functional Requirements
- List past speaking sessions: date, topic, overall band.
- Clicking a session shows the full evaluation breakdown (per-criterion scores).
- **Band score trend chart:** line chart of overall band over the last 10 sessions.
- **Share** button: copy a public link to session results.

### Non-Functional Requirements
- Shared result links are **publicly viewable without authentication**.

---

## 16. Writing Practice (Non-Exam)

**Surface:** `/chat` textarea / dedicated writing interface · **Access:** Authenticated (**Paid**)

### Functional Requirements
- Plain-text essay input (no rich formatting, no image upload, no OCR).
- On submit, evaluate across 4 criteria concurrently: Task Response, Cohesion, Vocabulary, Grammar.
- Display the essay with **inline colour-coded highlights**: red = grammar, blue = vocabulary, orange = cohesion, purple = task response.
- Hovering a highlight shows the specific issue + a suggested improvement (tooltip).
- Display per-criterion band scores (side panel with bar charts) and an overall band at the top.
- **"Show improved version"** button — generates a rewrite one band higher (paid).
- **Download feedback as PDF** button.

### Non-Functional Requirements
- **Paid-tier only.**
- Essay input capped at **5000 characters**; **5 essay evaluations/hour** per user.
- Character-level annotations map precisely to text spans (no off-by-one errors).
- Overall band = mean of 4 criteria, rounded to nearest 0.5.

---

# Subscription & Billing

## 17. Upgrade Prompt Modal

**Surface:** Inline in `/chat` on paid-feature access · **Access:** Free users

### Functional Requirements
- Appears when a free user requests a paid feature (CV review, speaking, writing, full exam simulations).
- Lists what paid access unlocks **and** what remains free.
- **Upgrade for $7/month** button leading to `/pricing`.

### Non-Functional Requirements
- Non-aggressive: appears **inline in chat**, not as a full-page takeover.
- Triggered by a gateway `403 {"error":"subscription_required","feature":...,"upgradeUrl":"/pricing"}`.

---

## 18. Pricing Page

**Route:** `/pricing` · **Access:** Authenticated

### Functional Requirements
- Free vs Paid tier comparison.
- **Subscribe** button → `POST /api/billing/create-checkout` → redirect to Stripe-hosted Checkout.

### Non-Functional Requirements
- Card data entered **only on Stripe** (PCI compliant — GOA never sees card data).
- Stripe test cards must work in staging.

---

## 19. Payment Confirmation

**Surface:** Redirect after Stripe success (`/chat?upgraded=true`) · **Access:** Authenticated

### Functional Requirements
- Confirmation page/banner shown after successful payment.
- All paid features unlocked immediately.

### Non-Functional Requirements
- Tier upgrade driven by a **verified Stripe webhook** (signature-checked); gateway Redis cache invalidated so the next request reflects paid tier.
- Failed payments (e.g. insufficient funds) return the user to `/pricing` with an error.

---

## 20. Manage Subscription

**Surface:** Link to Stripe Customer Portal · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Manage subscription** link → `POST /api/billing/portal` → Stripe-hosted portal (cancel, update payment method, view/download invoices).
- First-time subscribers (no Stripe customer ID) redirected to `/pricing` instead.
- **Grace-period banner:** *"Payment failed — update your payment method to keep access."* shown during the 3-day grace period; paid features remain accessible.

### Non-Functional Requirements
- Self-service billing handled entirely on Stripe.
- **3-day grace period** after a failed payment before automatic downgrade to free.
- Subscription lifecycle driven by Stripe webhooks (cancellation, payment failure/success, plan change).

---

# IELTS Exam Preparation

## 21. Exam Prep Dashboard

**Route:** `/exam` · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Academic vs General Training** toggle (persisted to the user profile).
- 4 skill cards — Reading, Listening, Speaking, Writing — each showing the last band score (if any) and a **Start Exam** button.
- Empty state when no exams have been taken.
- Supports deep-linking to a skill with a question type pre-filtered (from results pages).

### Non-Functional Requirements
- **Paid-tier only** (`/api/exam/*` requires paid subscription).
- **Exam start rate limit:** max 3 sessions per user per hour (prevents question-bank farming).

---

## 22. Exam Shell (Shared)

**Surface:** Full-screen wrapper for all exam skill UIs · **Access:** Authenticated (**Paid**)

### Functional Requirements
- Full-screen layout with skill name + exam-type badge.
- **Countdown timer** top-right; receives total seconds from server, counts down client-side, **turns red at 5 minutes remaining**.
- **Submit** button with a confirmation modal.
- **Auto-submit** when the timer reaches 0.
- Sends a heartbeat `PATCH /sessions/:id/heartbeat` every 60 seconds.
- Exam state persisted in **sessionStorage** — page refresh resumes the exam and re-fetches remaining time from the server.
- Per-skill results state machines:
  - **Reading/Listening:** submitted → results (instant).
  - **Speaking:** in_progress → part1_done → part2_done → part3_done → evaluating (overlay) → results.
  - **Writing:** task1_submitted → task1_evaluating → task1_done (side panel) → task2_writing → task2_submitted → task2_evaluating → combined_results.

### Non-Functional Requirements
- **Mobile responsive down to 768px (tablet) minimum** for exam mode.
- Remaining time is always authoritative from the server (refresh-safe).
- Answer key never sent to the client — grading is server-side only.

---

## 23. Reading Exam

**Surface:** Inside Exam Shell · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Split-panel:** passage text (left, scrollable) + questions (right, independently scrollable).
- 3 passages, 40 questions; **Section 1/2/3 tabs** preserve answers when switching.
- **Passage highlighting:** user can select text to highlight (local-only, not submitted).
- All Cambridge question-type renderers:
  - Multiple Choice (radio)
  - Matching (dropdown or drag-drop)
  - True/False/Not Given (3-button toggle)
  - Fill-in-the-Blank (inline text input)
  - Short Answer (text input)
- **Question navigation sidebar:** numbered circles, filled = answered / empty = unanswered, click to jump.
- Submit modal warns of unanswered questions with the exact count.
- Submit via `PUT /api/exam/reading/:sessionId/submit` with all 40 answers.

### Non-Functional Requirements
- Server selects a **random unseen** test (Cambridge IELTS 14–18) per user.
- **Timer:** 3600 seconds.
- Grading is **pure Python, < 100ms**, case-insensitive for text answers.
- Raw score → IELTS band via the official Academic/General conversion table.

---

## 24. Listening Exam

**Surface:** Inside Exam Shell · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Custom HTML5 audio player with seeking disabled** (progress bar display-only — cannot skip ahead).
- **Sequential section progression:** 4 sections; **Next Section** appears only after the current audio ends.
- Questions displayed alongside the audio; user answers while listening.
- **Scratch pad** for notes (not submitted).
- 30-second silence gap between sections, shown as a countdown.
- **10-minute answer transfer period** after all audio ends, before final submission.
- Same question-type renderers as Reading.

### Non-Functional Requirements
- Audio delivered via **per-session pre-signed S3 URLs** (valid ~2 hours; not shareable across sessions).
- Seeking blocked both via UI and by intercepting programmatic `currentTime` changes.
- **Timer:** 2400 seconds (40 minutes).
- Official Listening band conversion table (distinct from Reading).

---

## 25. Speaking Exam

**Surface:** Inside Exam Shell · **Access:** Authenticated (**Paid**)

### Functional Requirements
- Strict IELTS 3-part structure with transition/instruction screens between parts:
  - **Part 1 (Interview):** 4 questions, one at a time; **Record Answer** → **Next Question**.
  - **Part 2 (Long Turn):** cue card (topic + 3 bullets); **60s preparation countdown** (recording paused) → automatic **120s speaking timer**.
  - **Part 3 (Discussion):** 4–5 questions, same interface as Part 1; ends with **Submit Exam**.
- **Waveform visualiser** during recording.
- After each part: a **neutral confirmation screen** (*"Part 1 complete. Ready for Part 2?"*) — **no score, no feedback, no hints** (enforced UI-side and server-side).
- After Part 3 submit: full-screen **evaluating overlay** (*"Analysing your performance across all 3 parts…"*) — blocks interaction until results are ready.

### Non-Functional Requirements
- **Paid-tier only.**
- Part-2 prep timer auto-transitions to the speaking timer at 0 without user action.
- Transcripts stored silently after each answer; **holistic** evaluation uses all 3 parts together (4 agents in parallel).
- Evaluation typically takes 5–8 seconds.

---

## 26. Writing Exam

**Surface:** Inside Exam Shell · **Access:** Authenticated (**Paid**)

### Functional Requirements
- Two-panel layout: **Task 1** and **Task 2** as tabs.
- **Academic Task 1:** stimulus chart image above the textarea, with a **zoom** button.
- **General Training Task 1:** letter-scenario text above the textarea.
- **Live word counter** per task: orange below target (140 / 240), green at target (150 / 250).
- Recommended-time indicator based on elapsed time (*"Suggested: 20 min for Task 1"*).
- Plain textarea — no rich formatting (matches the real IELTS computer test).
- **Submit Task 1** → compact results card (band + top issue per criterion), defaulting to collapsed; **Task 2 editor stays fully active** (no blocking spinner for Task 1).
- **Submit Task 2** → standard 4-agent evaluation.

### Non-Functional Requirements
- **Paid-tier only.**
- **Timer:** 3600 seconds total.
- Task 1 evaluation reads the chart image (GPT-4V) to verify the user described the correct data.
- Final band uses explicit **33% / 67% Task 1/Task 2 weighting**.

---

## 27. Exam Results

**Surface:** Shown after each exam (per skill) · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Overall band score** prominently displayed.
- **Reading / Listening:** section breakdown (per-passage/section scores as progress bars); per-question view (user answer vs correct answer, green/red); **question-type breakdown** (e.g. *"95% on Multiple Choice but 62% on TFNG"*) with the weakest type highlighted and a **"Practise this type"** button (deep-links to `/exam` pre-filtered).
- **Speaking:** per-criterion cards (Fluency / Lexical / Grammar / Pronunciation), each with band score, overall feedback paragraph, **Part 1 / 2 / 3 tabs** (per-part narrative), and **transcript quote examples with inline issue annotations**.
- **Writing:** Task 1 and Task 2 cards side-by-side; combined band shown as an **explicit formula** (e.g. *"(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0"*); inline colour-coded highlights on both tasks; under-minimum word-count warning with penalty explanation.
- **Improvement tips section** on every results page: 3 specific, actionable tips based on the weakest criterion/section, linking back to `/exam`.

### Non-Functional Requirements
- After completion, the user's band scores are written to their profile (used for personalised recommendations and opportunity matching).
- Correct answers revealed only **after** submission.

---

## 28. Exam Progress / History

**Surface:** `/profile` → **Exam Progress** tab · **Access:** Authenticated (**Paid**)

### Functional Requirements
- **Score trend chart** per skill: line chart of the last 10 exam bands.
- **Weak areas panel:** one card per skill showing the lowest-scoring section/criterion (e.g. *"Reading: Section 3 — TFNG: 54%"*) with a **Practise Now** button → `/exam`.
- **Recent exams list:** last 5 with skill icon, Academic/General badge, band, date, **View Results** link.
- **Estimated overall IELTS band:** average of the last exam per skill, with a *"based on practice exams"* disclaimer.
- **Empty state** with a **"Start your first practice exam"** CTA when no exams exist.

### Non-Functional Requirements
- Data sourced from `GET /users/:id/progress` and `/exam-history` (paginated, 20/page).
- Trend data returned in correct chronological order.
- Real measured bands feed the opportunity-scoring pipeline (more accurate than self-reported).

---

# Cross-Cutting

## 29. In-App Notifications

**Surface:** Notification badge across the authenticated app · **Access:** Authenticated

### Functional Requirements
- Notification **badge** visible on the user's next visit after a scholarship match.
- Notification content includes scholarship/program name, deadline, match reason, and a direct link to the relevant checklist on GOA.
- Complements the email channel (AWS SES) — an in-app notification record is created per match.

### Non-Functional Requirements
- Driven asynchronously by the weekly ingestion + scholarship-matcher pipeline (background, eventual).
- A user is notified at most once per match cycle, and only for deadlines within 90 days.

---

## Appendix — Platform-Wide Non-Functional Requirements

These apply across all authenticated screens unless a screen states otherwise.

| Category | Requirement |
|---|---|
| **Authentication** | JWT in httpOnly cookie (1h) + refresh token; passwords bcrypt-hashed; unauthenticated access to gated routes redirects to `/login`. |
| **Authorization** | Paid features gated at the gateway (403 `subscription_required`); exam session-ownership validated server-side (403 on mismatch). |
| **Rate Limiting** | 20 RAG queries/hour; 5 essay evals/hour; 30 min speaking/day; 3 exam starts/hour; gateway WAF 1000 req/min per IP. |
| **Performance** | Chat P95 < 5s; speaking P95 < 3s; essay eval P95 < 30s; reading/listening grading < 100ms; system error rate < 1%. |
| **Security (AI)** | Prompt-injection sanitisation; input length caps (chat 2000, essay 5000 chars); PII detection/redaction in outputs; system-prompt-leak prevention; OWASP LLM Top 10 guardrails. |
| **Accessibility** | ARIA labels and full keyboard navigation on all forms; landing-page Lighthouse a11y > 90. |
| **Responsiveness** | Standard app responsive; exam mode requires a minimum 768px (tablet) viewport. |
| **Reliability** | Friendly, non-raw error states for service unavailability; exams refresh-safe via sessionStorage + server time; auto-submit on timer expiry. |
| **Transport** | HTTPS-only (HTTP → 301 HTTPS); served via CloudFront/WAF/Route 53. |
| **Privacy** | Card data handled only by Stripe (PCI); users can wipe stored conversational memory. |

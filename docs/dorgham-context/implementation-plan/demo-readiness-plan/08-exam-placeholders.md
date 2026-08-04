# 08 — Exam Placeholder Replacement

## Objective

Prevent the Listening and Speaking exam cards from ever reaching their
current placeholder rendering, and replace that placeholder with a
deliberately designed "coming soon" panel for the case it is still reached
by direct navigation.

## Background

`/exam` presents four visually equal, attractive skill cards: Reading,
Listening, Writing, Speaking. Two of them — Listening and Speaking — lead,
inside the exam shell, to a dashed grey rectangle reading *"Interactive
Simulation Workspace"* with the caption *"Standard exam interface containing
simulation questions."* If anyone clicks either card during the demo, the
demo's credibility is spent in that instant.

This gap is not an oversight — it is a genuine, documented backend
limitation. `services/gateway/server.go` (around the exam route
registration) explicitly documents that the audio delivery endpoint needed
for Listening does not exist yet on the exam service side and is blocked on
work owned by a different team. The correct fix here is not to hide this
fact, but to **present it deliberately** rather than let a placeholder
component reveal it accidentally, mid-demo.

## Why This Matters

"Reading is complete; Listening and Speaking are next" is a credible,
professional engineering narrative that a technical reviewer will accept
without friction. A dashed grey box with placeholder copy, discovered live,
is not — it reads as either an oversight or an attempt to hide an unfinished
feature behind an equally-weighted card. The fix here is cheap and directly
converts a liability into a talking point.

## Scope

**In scope:**
- Adding a per-skill availability flag to the `/exam` dashboard's skill
  card configuration.
- Disabling the "Take Exam" action and adding a "Coming soon" badge for
  Listening and Speaking specifically.
- Replacing the exam shell's dashed-placeholder fallback branch with a
  properly designed panel, for the case where the shell is reached directly
  (e.g. via a stale `sessionStorage` entry or a manually-typed URL).
- Ensuring the panel's "back" action clears any stale exam-session state
  rather than looping.

**Out of scope:**
- Building the actual Listening or Speaking exam UI — both are
  multi-sprint, backend-blocked efforts tracked in the Phase 3 backlog.
- Fixing the underlying audio pre-signing gap in the exam service — that is
  the actual multi-sprint work this task is deliberately not attempting.

## Files Expected to Change

```
services/frontend/app/exam/shell/page.tsx
services/frontend/app/exam/page.tsx
services/frontend/components/exam/ComingSoonPanel.tsx        (new)
```

## Detailed Implementation Plan

Implement two layers of defense, since either one alone leaves a gap.

**Layer 1 — prevention at the dashboard.** Add a per-skill availability flag
to the `skillCards` configuration array in `app/exam/page.tsx`. For
Listening and Speaking specifically, render a "Coming soon" badge in place
of (or alongside, disabled) the "Take Exam" button. This is the primary
fix: it means the placeholder branch inside the shell is never reached in
ordinary use at all. It also has a secondary, non-cosmetic benefit — it
prevents a needless `POST /api/exam/sessions` call, which consumes one of
the exam service's three-sessions-per-hour rate-limit slots. That is a real
risk if a presenter clicks around exploring the app before going live on
stage, and could exhaust the rate limit before the actual Reading-exam demo
beat.

**Layer 2 — a designed fallback if reached anyway.** Replace the dashed
grey box in the shell's `examConfig.skill !== "Writing" && !== "Reading"`
fallback branch with a new, proper component (`ComingSoonPanel`): a clear
heading naming the specific skill, one sentence describing what's planned,
a short bulleted list of the concrete capabilities already scoped for it
(for Listening: seek-disabled audio player, sequential section
progression, a scratch pad, a 10-minute answer-transfer period; for
Speaking: the strict 3-part IELTS structure, a 60-second preparation
timer, a live waveform visualizer, holistic 4-agent evaluation), and a
button that returns to `/exam`. Style it in the same card language as the
rest of the exam shell — this should look like a deliberate part of the
product, not an error state.

## Edge Cases

- If a session for Listening or Speaking already exists in
  `sessionStorage` from prior manual testing (a realistic scenario during
  development and rehearsal), the exam dashboard's existing resume effect
  will still push the user into the shell directly, bypassing the
  dashboard's Layer 1 prevention entirely. The panel must render cleanly
  in this case.
- The panel's "back to `/exam`" action must **clear the
  `active_exam_session` sessionStorage key**, or the user will be bounced
  in a redirect loop between `/exam` and `/exam/shell` — this is the exact
  same underlying trap addressed for the general case in
  [10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md);
  solve the shared root cause once, and make sure this panel's action uses
  that same fix rather than a second, parallel implementation.

## Acceptance Criteria

- Listening and Speaking cards on `/exam` display a "Coming soon" badge and
  cannot initiate a session (the action is either hidden or disabled, not
  merely mislabeled).
- No network request fires when a disabled skill card's action is clicked.
- The exam shell's fallback branch renders the new designed panel, never
  the dashed-grey placeholder.
- The panel's back action clears `active_exam_session` and returns to
  `/exam` without triggering a redirect loop.

## Verification Steps

1. Open `/exam`; confirm Reading and Writing remain fully actionable while
   Listening and Speaking show a visible "Coming soon" badge.
2. With devtools Network open, click the disabled action on a Listening or
   Speaking card; confirm no request is issued.
3. Manually navigate to `/exam/shell?session=<a listening or speaking
   session id>` directly in the URL bar; confirm the new designed panel
   renders (not the dashed box).
4. Click the panel's back action; confirm it returns cleanly to `/exam`
   with no redirect loop, and that `sessionStorage.active_exam_session` is
   cleared afterward.

## Dependencies

Shares a root-cause fix (stale/invalid `active_exam_session` handling) with
[10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md).
Implement that shared fix once and have both tasks' verification confirm
against it — do not implement two separate resolutions for the same
underlying redirect-loop condition.

## Estimated Effort

45 minutes.

## Risk

**Low.** Isolated to one conditional branch of the exam shell plus badge
rendering on the dashboard's card configuration. Does not touch the Reading
or Writing branches of the shell.

## Status

Completed. New `components/exam/ComingSoonPanel.tsx` (skill-specific
heading, planned-capability bullets for Listening/Speaking, back action).
`app/exam/page.tsx`'s `skillCards` gained an `available` flag (Reading/
Writing `true`, Listening/Speaking `false`); unavailable cards render a
non-interactive "Coming soon" badge instead of the "Take Exam" button.
`app/exam/shell/page.tsx`'s dashed-placeholder fallback branch replaced
with `<ComingSoonPanel>`; its back action clears
`sessionStorage.active_exam_session` before navigating to `/exam` (doc 08's
own required fix, implemented directly since doc 10 — the document this
one names as owning that shared root cause — has not been implemented
yet).

Verified live with a real headless-browser session against a real
authenticated (paid-tier) account: Listening/Speaking show "Coming soon"
and no `POST /api/exam/sessions` request fires when clicked; a manually
inserted Listening `exam_sessions` row (this environment has no listening
question bank seeded, so one could not be created through the ordinary
create-session API — see Blockers) was used to navigate directly to
`/exam/shell?session=...`, confirming the old placeholder text is gone,
`ComingSoonPanel` renders with Listening-specific capability bullets, and
its back action returns to `/exam` with `sessionStorage` cleared and no
redirect loop.

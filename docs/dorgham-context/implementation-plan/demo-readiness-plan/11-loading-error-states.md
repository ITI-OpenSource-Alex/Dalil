# 11 — Loading and Error State Polish

## Objective

Replace every raw browser-default loading/error surface on the exam path —
a native `alert()`, bare unstyled `<div>` loading/error text, and an
evaluation overlay that can get permanently stuck — with styled,
consistent, recoverable states.

## Background

Several failure and loading paths currently fall back to raw defaults:

- `/exam`'s `startExam` failure path calls `alert("Unable to start exam.")`
  — a native browser dialog box.
- `/exam/results` renders bare `<div>Loading...</div>` and `<div>{error}</div>`
  for its loading and error states, with no styling at all.
- `/exam/shell`'s `executeSubmission` catch block only calls
  `console.error(err)` on failure — it does not reset `status`, so the
  full-screen "Analyzing performance…" overlay (shown while
  `status === "evaluating"`) **never clears** if the submit request fails,
  leaving the user stuck behind a full-screen overlay with no visible way
  out short of a reload.
- A stray `console.log(result)` sits in the same function, left over from
  development.

## Why This Matters

A native `alert()` box on a shared screen or projector is one of the most
jarring artifacts available in a web application — it visually announces
"this is a raw error," unstyled and inescapable until dismissed. An overlay
that never clears on failure is worse: it is a dead end with no recovery
path at all short of reloading the page mid-presentation. Both are cheap to
fix and both sit directly on the exam flow, which is the demo's strongest
asset — these are exactly the failure modes that would undermine trust in
that flow specifically if triggered live.

## Scope

**In scope:**
- Extending the shared `Skeleton` component to support size overrides, so
  it can be reused for block-shaped loading states, not just single text
  lines.
- Replacing the `alert()` on `/exam` with an inline, dismissible error
  banner with a retry action.
- Replacing the bare loading/error divs on `/exam/results` with a proper
  skeleton and the same styled error/retry pattern already used elsewhere
  in the app.
- Fixing `executeSubmission`'s catch block on `/exam/shell` to reset
  `status` and surface a visible, retryable submission-failure message.
- Removing the stray `console.log`.

**Out of scope:**
- The known timer/duplicate-submit race documented in
  `GOA-058_remaining_work.md §3.4` — adding an in-flight-submission guard
  here would be a reasonable bonus but is explicitly not required for this
  task; do not attempt it under the same time budget.
- Any change to the Reading exam's own submit/loading states, which are
  already correct and are out of scope for this task entirely.

## Files Expected to Change

```
services/frontend/app/exam/page.tsx
services/frontend/app/exam/results/page.tsx
services/frontend/app/exam/shell/page.tsx
services/frontend/components/ui/skeleton.tsx
```

## Detailed Implementation Plan

**Extend `Skeleton`.** It is currently a single fixed-size component
(`h-4 w-full`, `animate-pulse`) with no configurable props, used today only
by `/profile`. Add optional size-control props (e.g. `className`, or
explicit `height`/`width`) so the same component can stand in for
block-shaped loading regions (cards, banners) as well as text lines. This
is the enabler for the results-page loading state below and should be built
generically enough to be reused anywhere else loading skeletons are needed
later, without inventing a second skeleton component.

**`/exam`.** Replace the `alert("Unable to start exam.")` call with an
inline, dismissible error banner rendered near the skill card grid,
containing a human-readable message and a Retry action that re-attempts
`startExam`. Preserve the existing per-card "Starting…" button-label
behavior, which is already correct and should not be touched.

**`/exam/results`.** Replace the two bare `<div>Loading...</div>` /
`<div>{error}</div>` states. The loading state should use the now-extended
`Skeleton` component to approximate the actual results layout (a banner
block, then section blocks) — this reads far better than plain text and
matches the loading treatment already used elsewhere in the app. The error
state should reuse the same styled error/retry card pattern already present
in `ChecklistView` and `/profile` (red-bordered card, message, Retry
button) rather than inventing a third distinct error style.

**`/exam/shell`.** In `executeSubmission`'s catch block, add: resetting
`status` back to a non-`"evaluating"` value on failure, and surfacing a
visible, styled failure message with a retry affordance — this converts a
permanently stuck full-screen overlay into a recoverable state. Also remove
the stray `console.log(result)` left in the success path of the same
function.

## Edge Cases

- The exam timer's auto-submit path also calls `executeSubmission` when the
  clock reaches zero. Confirm a failure occurring via that path behaves
  identically to a failure via the manual "Submit Exam" button — both must
  clear the overlay and offer recovery, not just the manually-triggered
  path.
- `GOA-058_remaining_work.md §3.4` documents a known race where timer
  expiry can trigger a second, concurrent submit if a manual submit was
  already in flight. This task does **not** need to fix that race — it is
  explicitly out of scope here — but be aware of it so the failure-handling
  change doesn't mask or complicate diagnosing it later; note it, don't
  attempt to solve it under this task's time budget.
- Confirm the Retry action on `/exam`'s new error banner doesn't allow
  double-submission if clicked rapidly — a simple disabled-while-retrying
  state is sufficient; a full in-flight-request guard is not required here.

## Acceptance Criteria

- No `alert()` call remains anywhere under `services/frontend/app/`.
- No unstyled `<div>Loading...</div>` or bare error `<div>` remains on the
  exam results route.
- A failed exam submission clears the "Analyzing performance…" overlay and
  presents a visible, retryable error instead of leaving the user stuck.
- Error and loading visual treatment is consistent across `/exam`,
  `/exam/results`, `/profile`, and the checklist page.
- `Skeleton`'s existing usage on `/profile` continues to render unchanged
  after the prop additions.

## Verification Steps

1. Temporarily stop the exam service; from `/exam`, click "Take Exam" on
   Reading or Writing; confirm a styled inline banner appears (not a native
   alert), with a working Retry action.
2. Restart the exam service; click Retry; confirm the session now starts
   successfully.
3. Navigate to `/exam/results?session=<an invalid session id>`; confirm a
   styled error card renders, not a bare string.
4. Start an exam, stop the exam service mid-session, then submit; confirm
   the "Analyzing performance…" overlay clears and a styled, retryable
   error message appears instead of a permanently stuck screen.
5. Confirm `/profile`'s existing skeleton loading state still renders
   correctly after the `Skeleton` component's prop changes.

## Dependencies

None blocking. Can be implemented independently of every other task, though
it is logically related to
[10 — Error Boundaries and Crash Guards](10-error-boundaries-crash-guards.md)
in that both harden the exam flow against failure — they address different
failure classes (render throws vs. handled request failures) and do not
share code.

## Estimated Effort

1 hour.

## Risk

**Low.** Presentational changes plus small state corrections. The overlay
fix changes control flow inside `executeSubmission` — explicitly verify the
success path still navigates to the results page correctly after this
change, since that's the one place a mistake here could regress a
currently-working path.

## Status

Completed. `Skeleton` extended with an optional `className` prop
(defaulting to the original `h-4 w-full`, so `/profile`'s existing calls
render unchanged). `/exam`'s `alert("Unable to start exam.")` replaced
with the same inline, dismissible, retryable banner pattern already used
for the profile-loading guard, tracking which skill was attempted so Retry
re-attempts the right one. `/exam/results`'s bare `Loading...`/`{error}`
divs (including the outer `Suspense` fallback) replaced with `Skeleton`
blocks and the same red-card error/retry pattern used on `/profile` and
`ChecklistView`; a `retryCount` state re-runs the existing load effect
rather than duplicating its fetch logic. `/exam/shell`'s
`executeSubmission` now resets `status` back to `"in_progress"` and shows
a visible, retryable error banner on failure instead of only logging
(which left the full-screen overlay stuck); the stray `console.log(result)`
was removed.

**Discovered finding, documented rather than silently worked around:**
verifying the failure path required no simulation — `submitSession`'s
request shape (`{answers: {task1, task2}}`,
`services/frontend/lib/exam-api.ts`) does not match what the backend's
Writing submission handler actually requires
(`{task_number, essay_text}`, `_submit_writing` in
`services/exam/app/services/session_service.py`), confirmed directly via
a real submission attempt returning `400 "essay_text and task_number are
required for writing submissions"`. This is a **pre-existing protocol
mismatch this task did not introduce** (the request-building code was not
touched) and was not authorized to fix (a real request/response
restructuring, not "loading/error state polish"). This document's Risk
section assumed the success path currently works; live verification shows
it does not — real Writing submissions fail every time, and this task's
fix is what makes that failure recoverable (overlay clears, real error
shown, exam remains usable) rather than a stuck full-screen overlay.
Flagged as a follow-up in the Final Report.

Verified live: a real exam-service outage (container actually stopped, not
mocked) produces the styled banner with no native `alert()`, and Retry
succeeds once the service is healthy again; `/exam/results` with an
invalid session shows the styled error card; a real Writing submission
against the exam service's real (mismatched) contract clears the overlay
and shows a visible, retryable error with the exam still usable; a full
Reading exam cycle (unaffected by this task) still renders correctly;
`/profile`'s skeleton still renders its original 3 pulse blocks unchanged.

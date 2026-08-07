# 02 — Writing Practice Infinite Spinner Fix

## Objective

Fix the Writing Practice flow in `/chat` so that a submitted essay either
resolves to a real evaluation or fails visibly with a recoverable error —
never hangs on a spinner forever.

## Background

Clicking the pen icon in `/chat`, submitting an essay, and having the
evaluation panel spin indefinitely is the worst possible failure mode for a
live demo: it is silent, looks like a hang rather than an error, and its
only recovery today is a full page reload in front of the audience.

Root cause, traced end to end:

- `chat-shell.tsx`'s `writing_url` event handler sets `writingLoading(true)`
  and then calls `streamWritingEvaluation(event.sseUrl, handleWritingEvent).catch(console.error)`.
- The SSE URL that orchestration hands back points at the **gateway**
  (`/api/writing/essays/:id/evaluate`), which sits behind JWT auth
  middleware and a `RequirePaid` subscription check.
- `streamWritingEvaluation` (in `lib/writing-stream.ts`) performs a bare
  `fetch(sseUrl)` with **no `credentials: "include"`**, so the httpOnly auth
  cookie is never attached to the request.
- The gateway therefore returns 401 before any event stream starts. The
  fetch's non-`ok` response throws inside `streamWritingEvaluation`, which
  is caught only by `.catch(console.error)` — a dead end that never touches
  `writingLoading`.
- The evaluation panel behind this bug (`writing-evaluation-panel.tsx`, 264
  lines: per-criterion bar charts, inline colour-coded issue highlighter,
  "Show improved version" toggle, PDF download) is fully built and
  currently unreachable because of these two lines.

## Why This Matters

This is a two-line root cause with an outsized demo impact: it silently
kills an entire, otherwise-complete feature, and it fails in the worst
possible way (a hang, not an error) at the worst possible time (live, with
no recovery short of a reload). It is also low-risk to fix — the change is
purely additive (attaching a credential, resetting a state flag on an
existing failure path) and cannot break any currently-working request.

## Scope

**In scope:**
- Attaching credentials to the Writing SSE fetch so authenticated, paid
  requests succeed.
- Ensuring every failure path (network rejection, non-2xx response, and the
  existing `handleWritingEvent`'s `"error"` case) resets `writingLoading`
  and surfaces a visible, dismissible error in the writing panel.
- Clearing that error state when a new essay is submitted or writing mode is
  cancelled.
- A small unit test pinning the `credentials: "include"` regression.

**Out of scope:**
- Any change to the gateway's auth/subscription middleware.
- Any change to the orchestration routing logic that produces the SSE URL.
- Building out subscription-tier UX (upgrade modal, etc.) — that is
  explicitly out of scope for this demo per the Demo Readiness Review.

## Files Expected to Change

```
services/frontend/lib/writing-stream.ts
services/frontend/components/chat/chat-shell.tsx
services/frontend/components/chat/writing-evaluation-panel.tsx
services/frontend/test/unit/  (new test file for writing-stream.ts)
```

## Detailed Implementation Plan

**1. `writing-stream.ts`** — add `credentials: "include"` to the fetch
options passed to the SSE request. While making this change, also improve
the existing non-`ok` throw so its message carries the HTTP status code —
this lets a 401 (not logged in / not paid) read differently from a 500
(service unavailable) at the call site, rather than both collapsing into an
identical generic message. Do not swallow or discard the status code.

**2. `chat-shell.tsx`** — the `writing_url` event case currently does:

```
setWritingLoading(true);
streamWritingEvaluation(event.sseUrl, handleWritingEvent).catch(console.error);
```

Replace the bare `.catch(console.error)` with a handler that:
- Sets `writingLoading` back to `false`.
- Sets a new `writingError` state string describing the failure in
  user-facing terms (distinguish "you need to be logged in / upgrade" from
  "something went wrong — try again" where the status code allows it).

Introduce this `writingError` state alongside the existing
`writingEvaluations` / `writingOverallBand` / `inlineIssues` /
`improvedEssay` state, and pass it into `WritingEvaluationPanel` as a new
optional prop.

Also update the existing `handleWritingEvent`'s `"error"` branch — it
currently resets `writingLoading` correctly but discards `event.error` to
`console.error` only. Route that message into the same `writingError` state
so both failure paths (network/auth failure vs. an in-stream error event
from the writing service) surface identically to the user.

**3. `writing-evaluation-panel.tsx`** — accept the new `writingError` prop
and render it as an inline alert above the criterion bars when present.
Reuse the existing `components/speaking/inline-alert.tsx` component for
this rather than authoring a second, visually inconsistent alert style —
the codebase already has one alert pattern; don't add a second.

**4. Reset on resubmission.** `handleEssaySubmit` already resets
`writingEvaluations`, `inlineIssues`, and `improvedEssay` before sending a
new essay. Add `writingError` to that same reset list — otherwise a stale
error banner from a previous failed attempt survives visually into the next,
successful submission. Also clear it when the user cancels writing mode via
`EssayComposer`'s `onCancel`.

## Edge Cases

- A slow network could theoretically resolve the fetch as `ok` after a long
  delay — the existing spinner behavior for a genuinely slow-but-successful
  stream should be left untouched; this fix only targets the *failure*
  paths that currently strand the loading state permanently.
- If `writingError` is set and the user immediately reopens writing mode
  without submitting a new essay, the stale error should not reappear —
  clearing on `onCancel` (not just on next submit) covers this.
- Verify the fix does not change behavior for an already-working,
  authenticated, paid request — the credentials addition should be
  transparent when auth already exists.

## Acceptance Criteria

- The Writing SSE fetch request includes the auth cookie (verifiable in
  browser devtools → Network → Request Headers → `Cookie` is present).
- With a paid, authenticated user, submitting an essay streams criterion
  events progressively and the panel resolves to a complete evaluation.
- With an unauthenticated user (or a free-tier user, depending on gateway
  config), the spinner stops within one round trip and a visible inline
  error appears in the writing panel — not just a console log.
- Submitting a second essay after a prior failure clears the earlier error
  banner.
- `writingLoading` is `false` in every terminal state: success, an `"error"`
  SSE event, and a network/auth rejection.

## Verification Steps

1. `docker compose up`; log in as a paid demo user in the browser.
2. Open `/chat`, click the pen icon, paste a roughly 280-word essay, submit.
3. In devtools → Network, filter for the `evaluate` request; confirm it
   carries a `Cookie` header and returns `200 text/event-stream`.
4. Confirm criterion bars populate progressively as events arrive and the
   overall band renders at the end.
5. Open an incognito window with no session, repeat steps 2–3; confirm the
   spinner stops promptly and a visible inline error banner appears (not
   just a console message), and that the essay composer remains usable to
   try again.
6. Submit a second, valid essay after the failed attempt in step 5 (log in
   first); confirm no stale error banner is visible.

## Dependencies

None. This is independent of every other Phase 1 document and can be
implemented in isolation.

## Estimated Effort

15 minutes implementation, plus a short unit test (~10 minutes).

## Risk

**Very Low.** Purely additive — the `credentials` flag cannot break a
request when auth is already absent (it simply attaches a cookie that may
or may not exist), and the `.catch` change only adds behavior to a path that
currently does nothing but log to the console.

## Status

Completed. `credentials: "include"` added to the Writing SSE fetch, with a
status-aware error message; `chat-shell.tsx` now resets `writingLoading`
and surfaces a `writingError` string on both failure paths (failed stream
open and an in-stream `"error"` event), cleared on resubmission and on
cancel; `writing-evaluation-panel.tsx` renders the error via the existing
`InlineAlert` component. A unit test pins the `credentials: "include"`
regression and the status-coded error message. Full frontend unit test
suite (32 tests, 7 files) and `tsc --noEmit` pass with no regressions.

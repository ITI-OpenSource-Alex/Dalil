# 10 — Error Boundaries and Crash Guards

## Objective

Add a global (and exam-scoped) error boundary, guard the exam shell's
unsafe array indexing, validate the chat history response shape, and fix
the stale-session redirect loop — so that no single unforeseen failure can
white-screen the entire application during the demo.

## Background

There is currently **no error boundary anywhere in the frontend tree**. Any
render-time throw takes down the whole page with no recovery path except a
manual reload. Three concrete, already-identified throw sites exist:

1. The exam shell's Writing branch dereferences
   `session.questions[0].questions[1].prompt` completely unguarded — a
   session whose question shape differs even slightly throws during render.
2. `chat-shell.tsx`'s mount-time history-loading effect calls `.map()`
   directly on the parsed response body with no validation that it is
   actually an array — a non-array 200 response throws.
3. `/exam`'s session-resume effect reads `active_exam_session` from
   `sessionStorage` and immediately redirects into the exam shell; if that
   stored session is stale or the shell then fails to load it, the shell
   redirects back to `/exam`, which redirects again — an infinite loop with
   no user-facing escape.

## Why This Matters

Of everything in this plan, an unhandled render throw during a live
presentation is the single most damaging possible failure — worse than any
individual broken feature, because it takes the *entire application* down
rather than one flow, with no visible path to recovery short of the
presenter reloading the page in front of the audience. A global error
boundary is comparatively cheap insurance against every throw site,
including ones not yet identified, not just the three enumerated above.

## Scope

**In scope:**
- A root-level `error.tsx` (Next.js App Router error boundary convention),
  and a second one scoped to `app/exam/` so an exam-specific crash doesn't
  discard the entire application chrome.
- Defensive guards around the exam shell's unsafe question-array indexing,
  with a designed fallback panel rather than a throw.
- Response-shape validation in the chat history loader.
- A fix for the stale `active_exam_session` redirect loop, including
  explicit try/catch around the sessionStorage read and an explicit
  resume/discard choice presented to the user instead of an automatic,
  silent redirect.

**Out of scope:**
- Comprehensive error-boundary coverage of every individual component —
  the root and exam-scoped boundaries are the two that matter most for
  demo risk; do not attempt to boundary-wrap every page under time
  pressure.
- The known timer/duplicate-submit race documented in
  `GOA-058_remaining_work.md §3.4` — tracked separately in the Phase 3
  backlog; not fixed here.

## Files Expected to Change

```
services/frontend/app/error.tsx                              (new)
services/frontend/app/exam/error.tsx                          (new)
services/frontend/app/exam/shell/page.tsx
services/frontend/app/exam/page.tsx
services/frontend/components/chat/chat-shell.tsx
```

## Detailed Implementation Plan

**Global error boundary.** Add `app/error.tsx` following the Next.js App
Router convention: a client component rendering a branded, calm "Something
went wrong" card with a reset action (using the boundary's provided `reset`
function) and a link back to a safe route (e.g. `/chat` or `/`). This
single file converts *every* unhandled render throw across the entire
application — including throw sites not yet identified in this review —
from a white screen into a recoverable, on-brand state. It is the highest
insurance-value item in this plan relative to its cost. Add a second,
narrower `app/exam/error.tsx` so a crash specifically inside the exam flow
doesn't discard the surrounding application chrome (sidebar, etc.) if that
distinction is easy to preserve; if not, the root boundary alone is
acceptable.

The boundary component itself must be a client component and must not
perform any data fetching or contain any logic that could itself throw —
keep it deliberately simple.

**Exam shell question-array guards.** In the Writing branch of
`app/exam/shell/page.tsx`, replace the unguarded
`session.questions[0].questions[1].prompt` access (and any other similarly
unguarded indexing into `session.questions` in that file) with optional
chaining and a clear fallback panel rendered when the expected prompts are
absent, rather than allowing the access to throw during render.

**Chat history validation.** In `chat-shell.tsx`'s mount effect, validate
that the parsed history response is actually an array before calling
`.map()` on it, and validate that each entry carries the expected `role`
and `content` fields, skipping (not rendering) malformed entries rather
than passing `undefined` values into `Message` objects.

**Stale-session escape.** In `app/exam/page.tsx`'s resume effect: wrap the
`sessionStorage.getItem("active_exam_session")` read and its `JSON.parse`
in a try/catch — a corrupted stored value currently throws unguarded during
the effect. On the exam shell side, when `getSession` fails to load a
resumed session, have the shell **clear the `active_exam_session` key**
before redirecting back to `/exam`, breaking the loop at its source rather
than just delaying it. Additionally, replace the current fully-automatic
redirect-on-resume with an explicit choice presented to the user ("Resume
in-progress exam" / "Discard") — this both closes the loop for good and
removes a surprising, unannounced redirect that could otherwise happen
mid-demo if a stale session exists from earlier testing.

## Edge Cases

- The error boundary must never itself be capable of throwing — no data
  fetching, no dependency on state that might be undefined in a crashed
  render tree.
- A malformed `active_exam_session` value (invalid JSON) must be handled
  distinctly from a well-formed but stale/nonexistent session id — both
  must terminate in a clean state, not a loop, but the try/catch only
  covers the parse failure case; the shell-side "clear key on load failure"
  fix covers the stale-but-valid-JSON case.
- Confirm this task's stale-session fix is the single shared implementation
  also relied upon by
  [08 — Exam Placeholder Replacement](08-exam-placeholders.md)'s "back to
  `/exam`" action — do not implement the fix twice in two places.

## Acceptance Criteria

- A thrown render error anywhere in the tree displays the branded error
  card with a working reset action, not a white screen.
- The exam shell renders a designed fallback panel instead of throwing when
  the expected question array shape is absent or malformed.
- A malformed chat-history response does not throw and does not render
  `undefined` message bubbles into the chat.
- A corrupted or stale `active_exam_session` value never produces a
  redirect loop between `/exam` and `/exam/shell`.
- Users with a resumable session are offered an explicit resume/discard
  choice rather than being redirected automatically and silently.

## Verification Steps

1. In devtools, manually set `sessionStorage.active_exam_session` to
   invalid (non-JSON) text; load `/exam`; confirm no crash and no loop.
2. Set it instead to valid JSON referencing a nonexistent session id;
   confirm a clean recovery, with the stale key cleared afterward and no
   loop.
3. Temporarily induce a throw in a child component (for local verification
   only — remove afterward) to confirm the error boundary renders correctly
   and its reset action recovers the page.
4. Load the Writing branch of the exam shell against a session with only
   one question present (rather than the two the code currently assumes);
   confirm the designed fallback panel renders instead of a white screen.
5. Point the chat-history endpoint response at a non-array payload (e.g. via
   a temporary local mock) and confirm `/chat` does not throw and does not
   render broken message entries.

## Dependencies

Shares its stale-session fix with
[08 — Exam Placeholder Replacement](08-exam-placeholders.md); implement
that shared logic once. Otherwise independent of every other task in this
plan.

## Estimated Effort

1 hour.

## Risk

**Low.** All changes are additive — the error boundary is an entirely new
file, and the guards convert existing throw conditions into handled
fallback states rather than changing any currently-working control flow.

## Status

Completed. New `app/error.tsx` (root, with its own `<html>/<body>` per the
Next.js App Router convention for root-level error boundaries) and
`app/exam/error.tsx` (nested, scoped to `/exam` and its children).
`app/exam/shell/page.tsx`'s Writing branch now optional-chains
`session.questions[0]?.questions[N]?.prompt` with a fallback message per
task instead of throwing. `chat-shell.tsx`'s history loader now validates
the response is an array and that each entry has a valid `role`/`content`
before use, skipping malformed entries individually. The stale-session fix
spans both `app/exam/page.tsx` (try/catch around the sessionStorage
read/parse; the automatic redirect replaced with an explicit
resume/discard banner) and `app/exam/shell/page.tsx` (clears the key on a
failed session load). Per this document's own instruction not to
implement that clearing logic twice, both this fix and doc 08's
`ComingSoonPanel` back action now call one shared `clearActiveExamSession`
helper in `exam/shell/page.tsx`.

Verified live via real headless-browser sessions: malformed
`sessionStorage` JSON is silently discarded with no crash and no loop;
well-formed-but-stale sessions show the explicit resume/discard banner,
and resuming one that fails to load bounces back to `/exam` with the key
cleared and no further loop; a non-array chat-history response renders
`/chat` normally with no uncaught error; a Writing session with only one
question (not the assumed two) renders the fallback message instead of
throwing. The error boundaries were verified with real, temporarily
induced throws (added, tested, then fully reverted — confirmed via `git
diff` and a clean rebuild): a throw inside `/exam` is correctly caught by
the nested `app/exam/error.tsx` (not the root one), and a throw outside
`/exam` (tested on `/profile`) is correctly caught by the root
`app/error.tsx` — both render the branded card with a working reset
action.

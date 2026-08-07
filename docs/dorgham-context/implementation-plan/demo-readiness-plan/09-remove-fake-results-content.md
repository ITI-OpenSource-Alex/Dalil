# 09 — Remove Fabricated Results Content

## Objective

Remove the hardcoded, fabricated Writing feedback cards and static "Targeted
Action Plan" from the generic exam results page, so nothing on that page
misrepresents the actual result.

## Background

`app/exam/results/page.tsx`'s generic (non-Reading) results branch renders
two hardcoded cards — *"Task 1 (Band 7.0)"* and *"Task 2 (Band 7.5)"* — with
invented feedback paragraphs ("Data criteria categorization was logically
executed...", "Arguments presented exhibit robust support structures...")
and a static two-item "Targeted Action Plan," **regardless of the actual
result returned by the server**. The genuine overall band score and raw
score at the top of the page are real (`getResult(sessionId)`), but this
lower section is entirely fabricated content unconditionally rendered
underneath it.

## Why This Matters

Fabricated data displayed next to real data is worse than an empty state.
If a reviewer reads this section against a real band score that disagrees
with the invented "Band 7.0 / 7.5" text — which it will, since the text
never changes — the honest conclusion available to them is that the results
page is a mockup, which then casts doubt on the (genuinely real) Reading
results view sitting one navigation click away. This is a small, contained
fix with an outsized credibility payoff.

## Scope

**In scope:**
- Deleting the hardcoded Writing Task 1/Task 2 cards and the static action
  plan from the generic results branch.
- Replacing that section with either nothing, or a rendering of whatever
  real per-criterion data the result payload actually contains.

**Out of scope:**
- The Reading results branch (`ReadingResultsView`) — already correct,
  already real, must not be touched by this change.
- Building a full Writing-specific results view — that is part of the
  larger Writing exam UI work tracked separately in the Phase 3 backlog
  (merging `fix/GOA-058-writing-exam-ui`).

## Files Expected to Change

```
services/frontend/app/exam/results/page.tsx
```

## Detailed Implementation Plan

Delete the hardcoded Writing Task 1 / Task 2 cards and the two static
action-plan bullet points from the generic results branch. Keep the real
overall band score and raw score display at the top of the page unchanged —
those come from `getResult` and are genuine.

Before deciding what replaces the removed section, inspect the actual shape
of `result.section_scores` returned by a real (non-Reading) exam result.
Do not build a renderer for a field whose real, populated shape hasn't been
observed. Choose based on what's actually there:

- If `section_scores` (or an equivalent field) genuinely carries
  per-criterion detail for the skill in question, render that real data in
  place of the deleted cards.
- If it does not currently carry anything demo-usable, render nothing in
  that section rather than inventing a substitute — an absent section is
  honest; a differently-fabricated one is not an improvement.

Keep the "Return to Skills Workspace" link at the bottom of the page — it is
real, working navigation and should be preserved regardless of what happens
to the section above it.

## Edge Cases

- The Reading branch of this page returns early, before this code is
  reached, and must not be touched. Read the full control flow of the
  component before editing, so this deletion cannot accidentally regress
  the Reading results view, which is one of the two or three strongest
  assets in the entire demo.
- If the "no demo-usable data" case is chosen for the replacement, confirm
  the resulting empty section doesn't leave obviously dead whitespace or
  a broken-looking gap — a clean, deliberate empty state is preferable to
  either fabricated content or a visibly incomplete layout.

## Acceptance Criteria

- No hardcoded band number (e.g. "7.0", "7.5") or invented feedback
  paragraph remains anywhere in `app/exam/results/page.tsx`.
- The genuine overall band and raw score continue to render exactly as
  before this change.
- The Reading results view's behavior is byte-for-byte unaffected — no
  visual or functional regression.

## Verification Steps

1. Complete a full Reading exam through to its results page; confirm the
   view renders exactly as it did before this change (no regression).
2. Reach the generic (non-Reading) results branch for a Writing session, if
   reachable in the current build; confirm only real server-sourced data is
   displayed, with no hardcoded band numbers or invented text anywhere on
   the page.

## Dependencies

None. Fully independent — a deletion plus a small conditional replacement in
one file, isolated from every other task.

## Estimated Effort

20 minutes.

## Risk

**Very Low.** Deletion plus an honest empty (or real-data) state. The
Reading branch, which is the result view that matters most for the demo, is
untouched by this change.

## Status

Completed. The hardcoded "Task 1 (Band 7.0)" / "Task 2 (Band 7.5)" cards
and the static "Targeted Action Plan" were deleted from the generic
results branch. The removed section was replaced with nothing (not a
substitute renderer), per the doc's own explicit fallback instruction —
see the discovered finding below for why. The genuine band/raw-score
banner and the "Return to Skills Workspace" link are both untouched.

**Discovered finding, documented rather than silently worked around:**
inspecting the real backend response (`GET /sessions/:id/result`,
`services/exam/app/services/session_service.py`) shows that for
`skill_area === "writing"` — the *only* skill that can reach this generic
branch today (Reading has its own branch; Listening/Speaking aren't
startable per doc 08) — the server calls a completely different method
(`_get_writing_result`) that returns `{overall_band, tasks: {...}}`, not
`{band_score, raw_score, section_scores}` as `ExamResultResponse`
declares and as this page's "genuine" banner assumes. `section_scores`
does not exist at all in the real writing response; the real per-task
data lives under `tasks` instead. Per the acceptance criteria's explicit
instruction to keep the banner "exactly as before this change," it was
left untouched — meaning `result.band_score`/`result.raw_score` render as
`undefined` for a real writing result, a **pre-existing bug this task did
not introduce and was not authorized to fix** (out of this document's
file scope and explicit "keep unchanged" instruction). Flagged as a
follow-up in the Final Report.

Verified live: a full Reading exam (create → answer → submit → results)
renders identically to before, with no fabricated text anywhere on the
page in either branch.

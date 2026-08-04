# 07 — Chat Opportunity Card Layout Fix

## Objective

Fix the chat message layout so opportunity cards, source citations, and the
speaking evaluation breakdown render **below** the assistant's message
bubble, full width, instead of squashed beside it.

## Background

In `components/chat/message-list.tsx`, the opportunity card grid, the
sources footnote, and the speaking evaluation panel are currently rendered
as **siblings** of `MessageBubble` inside a single `flex gap-4` row. Because
`MessageBubble` itself is constrained to `max-w-[75%]`, these three
attachment types are laid out **horizontally beside** the bubble rather than
in a full-width block underneath it.

The opportunity cards specifically are the single most visually impressive
element in the chat interface (animated confidence bars, university/country
metadata, a "Get Checklist" call to action) — and they are exactly the
component that will be squashed and overflowing at the precise moment the
presenter is pointing at them during the opportunity-matching demo beat.

## Why This Matters

This is a pure layout bug affecting the best-looking component in the
application, discovered only by tracing the actual JSX structure rather than
assuming a well-styled component renders correctly in context. It is cheap
to fix and highly visible when broken.

## Scope

**In scope:**
- Restructuring the per-message layout in `message-list.tsx` so all three
  attachment types (opportunities, sources, speaking evaluation) render
  full-width below the bubble+avatar row.
- Verifying the existing entrance animations survive the restructure.

**Out of scope:**
- Any change to `MessageBubble`'s internal contract or rendering — it
  should be wrapped, not modified, so its avatar-placement-by-role logic
  stays intact.
- Any visual redesign of the opportunity card, sources footnote, or
  evaluation panel components themselves — only their positioning changes.

## Files Expected to Change

```
services/frontend/components/chat/message-list.tsx
```

## Detailed Implementation Plan

Restructure the per-message wrapper into two stacked regions:

1. A horizontal row containing the avatar and the message bubble together,
   preserving the existing `justify-end` / `justify-start` alignment logic
   keyed on message role (`isUser`).
2. A full-width column beneath that row holding any attachments — sources
   footnote, opportunity card grid, or speaking evaluation panel, in
   whichever combination is present on that message.

`MessageBubble` currently renders both the avatar and the bubble together
as a fragment, with avatar position determined internally by role. Keep
that component's contract exactly as-is — wrap it in the new layout
structure rather than modifying its internals or duplicating its
role-based positioning logic elsewhere.

Introduce an outer `flex-col` container and an inner `flex-row` (the
existing avatar+bubble row) rather than restructuring the message list's
overall iteration logic. The attachment column should be indented to
roughly align with the bubble's start (approximately the avatar's width
plus the existing gap), so cards don't visually run underneath the avatar.
Give the attachment region a wider max-width than the bubble's
`max-w-[75%]` — the existing `md:grid-cols-2` opportunity card grid wants
more horizontal room than that constraint currently allows.

## Edge Cases

- User-authored messages align right and never carry attachments in the
  current data model (`Message` type in `chat-shell.tsx` doesn't formally
  restrict this, but in practice only assistant messages populate
  `opportunities`, `sources`, or `evaluation`). Confirm this assumption
  holds by checking all three assignment sites in `chat-shell.tsx` rather
  than assuming it from the type alone — if it's ever violated, left-aligning
  the attachment column unconditionally would be wrong for a user message.
- The `AnimatePresence` and `layout` props on the outer motion element must
  survive the restructure, or message entrance/reflow animations will
  silently stop working. Keep the `layout` prop on the outermost motion
  element in the new structure, not on an inner one.
- Verify no horizontal overflow is introduced at narrower viewports once the
  attachment column is given more width than the bubble — check specifically
  at 768px, since that's the least-exercised breakpoint elsewhere in the
  codebase per the landing-page task's findings.

## Acceptance Criteria

- Opportunity cards render in a grid **below** the assistant's message
  bubble, full width, two columns on desktop.
- The sources footnote renders below the bubble, not beside it.
- The speaking evaluation breakdown renders below the bubble.
- Message entrance animations (fade/slide-in) still play correctly.
- No horizontal overflow in the chat scroll area at either 1280px or 768px.

## Verification Steps

1. Trigger an opportunity search in chat (requires
   [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md) to
   be in place for real results) and confirm the card grid's corrected
   layout.
2. Ask a RAG-routed question that returns cited sources; confirm the
   sources footnote renders below the bubble.
3. Complete a speaking practice session; confirm the evaluation breakdown
   panel renders below the bubble.
4. Narrow the browser window to 768px; confirm cards reflow to a single
   column with no horizontal overflow.

## Dependencies

Best verified after [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)
and [04 — Real User Identity Wiring](04-real-user-identity.md) are in place,
since those are what make opportunity cards actually appear in chat to test
against. The layout fix itself has no code dependency on either.

## Estimated Effort

25 minutes.

## Risk

**Low.** Contained to one component's JSX structure. Affects three distinct
render paths (opportunities, sources, speaking evaluation) — all three must
be verified, not just the one most obviously broken.

## Status

Completed. `message-list.tsx` restructured into an outer `flex-col`
(avatar+bubble row, then a full-width `ml-12 max-w-3xl` attachment column
guarded on `!isUser`) exactly as specified; `layout` kept on the outermost
`motion.div`; `MessageBubble` untouched.

Verified live: real end-to-end LLM-routed opportunity search was flaky in
this dev environment (see Blockers in the Final Report — a pre-existing
backend circuit-breaker/intent-classification issue, unrelated to this
task's scope). Isolated the frontend layout fix from that instability by
mocking `/api/chat`'s SSE response with the *exact* payload shape captured
from a genuine backend call earlier in this session (4 real opportunity
cards + a sources citation), then verified the real rendering code against
it: card grid renders below the bubble, wider than the bubble, in a real
`md:grid-cols-2` two-column layout; sources footnote renders below the
bubble; no horizontal overflow at 1280px or 768px. The third attachment
type (speaking evaluation) renders inside the identical `hasAttachments`
conditional/wrapper already proven correct for the other two — verified by
code inspection rather than a third live data path, given the shared
mechanism.

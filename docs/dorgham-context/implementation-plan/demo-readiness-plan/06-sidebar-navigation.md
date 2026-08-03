# 06 — Sidebar Navigation Cleanup

## Objective

Eliminate every dead (`href="#"`) sidebar link, either by pointing it at a
real, working route or by turning it into a clearly-labeled, non-interactive
"coming soon" entry — and fix the sidebar's active-route highlighting logic
in the process.

## Background

`components/ui/sidebar.tsx`'s `navItems` currently defines seven entries.
Four of them — Opportunities, Checklists, CV Review, and **Profile** — are
`href: "#"`. A single idle click on any of these during a live Q&A segment
appends a bare `#` to the URL and does nothing, which reads as broken
software. This is a real defect, not a cosmetic one: `/profile` is a fully
working page (real `GET /api/profile` call, skeleton loader, error/retry
state) and currently has **no working entry point anywhere in the
application**.

The sidebar renders on seven distinct routes (`/chat`, `/exam`,
`/exam/shell`, `/exam/results`, `/profile`, `/speaking/history`,
`/checklist/*`), so this hazard is present for most of the demo's runtime,
not just one screen.

Separately, the active-state logic (`pathname.startsWith(item.href)`)
behaves incorrectly for the `"#"` href entries and would also incorrectly
mark `/speaking/history` as active while actually on
`/speaking/share/:token`, since both share a `/speaking` prefix.

## Why This Matters

A dead sidebar link is exactly the kind of small, ambient defect a presenter
won't remember to avoid mid-demo, and it directly contradicts the narrative
that the product is finished. Converting the unavailable entries into
explicit "coming soon" indicators turns four hazards into a single,
deliberate, honest roadmap statement instead — which is a better story to
tell a reviewer than silence.

## Why This Matters (continued — Profile specifically)

The Profile page is not incomplete — it is fully functional and simply
unreachable. Its absence from the navigation graph is a pure omission bug,
not a scope gap, and is the single cheapest fix in this entire plan relative
to its impact.

## Scope

**In scope:**
- Extending `navItems` with an availability flag.
- Wiring Profile to its real, working route.
- Marking Opportunities, CV Review, and Checklists as clearly unavailable
  (visually muted, non-interactive, with a "Soon" indicator).
- Fixing the active-route highlighting logic.
- Confirming the mobile drawer still closes correctly after navigating via
  a real link.

**Out of scope:**
- Building an Opportunities index page or a Checklists index page — no such
  pages exist yet and building them is out of scope for demo prep (the
  Opportunities feature is demoed inline in chat; Checklists are reached via
  the "Get Checklist" button on an opportunity card).
- CV Review — genuinely unbuilt, out of scope entirely.

## Files Expected to Change

```
services/frontend/components/ui/sidebar.tsx
```

## Detailed Implementation Plan

Extend the `navItems` array's shape with an `available: boolean` field (or
equivalently, an optional `comingSoon` label). Then, per entry:

- **Profile** → point at `/profile`. It works today; it simply has no
  entrance anywhere else in the app.
- **Checklists** → there is no checklist *index* page — only the
  parameterized `/checklist/:programId` route exists, and it requires a
  specific program id that is only meaningfully known after an opportunity
  search. Mark this entry unavailable rather than guessing at a target.
  **Do not** point it at a hardcoded specific `/checklist/:id` — that would
  be a second, more dishonest kind of dead link, since it would silently
  break the moment the seeded demo program changes (see
  [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)).
- **Opportunities** and **CV Review** → mark unavailable.

Render unavailable entries as non-interactive elements (not `<Link>`
components), visually muted relative to the active navigation items, with a
small "Soon" chip or badge. This is the change that converts four
click-and-nothing-happens hazards into a single, deliberate feature-roadmap
statement the presenter can even point at directly if asked "what's next."

While in this file, fix the active-state matching logic: it should match
exactly for routes without children (e.g. `/chat`, `/profile`) and only
prefix-match where a route genuinely has child routes that should also
highlight the same nav entry. Verify this specifically resolves the
`/speaking/history` vs. `/speaking/share/:token` collision described above.

## Edge Cases

- The mobile drawer currently closes on click via an `onClick` handler
  attached to each `<Link>`. Since unavailable entries are being converted
  to non-interactive elements rather than links, confirm this doesn't
  silently orphan any drawer-closing behavior — it should be moot (there's
  nothing to click), but verify the drawer still closes correctly when a
  *real* link is tapped on mobile.
- If a future task adds a real Opportunities or Checklists index page, this
  component's `available` flag is the single place that needs to flip — the
  structure should make that trivial, not require re-deriving the whole nav
  item list.

## Acceptance Criteria

- No `href="#"` remains anywhere in `navItems`.
- Clicking Profile navigates correctly to `/profile`.
- Unavailable entries are visually distinct from active navigation items,
  carry a visible "Soon" indicator, and are not clickable / do not navigate
  anywhere.
- Active-route highlighting is correct across `/chat`, `/exam`,
  `/exam/shell`, `/profile`, and `/speaking/history` — and does not
  incorrectly highlight `/speaking/history` while on
  `/speaking/share/:token`.
- The mobile drawer still closes correctly after navigating via a real
  link.

## Verification Steps

1. From `/chat`, click every sidebar entry in turn. Confirm each either
   navigates correctly or is inert with a visible "Soon" indicator and no
   URL change.
2. Navigate to each of `/chat`, `/exam`, `/exam/shell`, `/profile`, and
   `/speaking/history` directly; confirm the correct sidebar entry is
   highlighted as active on each.
3. Navigate to a `/speaking/share/:token` URL; confirm the "Speaking
   History" sidebar entry is **not** shown as active.
4. At a 375px viewport, open the mobile drawer, tap Profile, confirm both
   correct navigation and that the drawer closes.

## Dependencies

None. Fully independent — a self-contained change to one component's
configuration and a small logic fix.

## Estimated Effort

30 minutes.

## Risk

**Very Low.** Navigation configuration plus small conditional rendering
logic; no data fetching, no shared state beyond what already exists.

## Status

Completed. `navItems` extended with `href: string | null` (`null` marks an
entry unavailable) and an opt-in `matchStrategy: "prefix"` for the two
routes with real child routes (IELTS → `/exam`, Speaking History →
`/speaking/history`); every other route now matches exactly. Unavailable
entries (Opportunities, Checklists, CV Review) render as inert `<div>`s
with a "Soon" chip. Profile now points at `/profile`.

Verified live with a real headless-browser session against a fresh,
authenticated account: no `href="#"` remains; all three unavailable
entries are non-interactive with a visible "Soon" badge; Profile
navigates correctly; active-route highlighting is correct on `/chat`,
`/exam`, `/profile`, and `/speaking/history`; the mobile drawer closes
after a real navigation at 375px.

One finding from verification: the `/speaking/history` vs.
`/speaking/share/:token` collision described in this document's
Background could not be reproduced — `app/speaking/share/[token]/page.tsx`
deliberately never renders `<Sidebar>` at all (it's a standalone public
page), so the collision is structurally unreachable regardless of the
matching logic, both before and after this change. The more precise
exact/prefix matching was still implemented exactly as specified, since it
is the more correct pattern in general and costs nothing. Documented in
the Final Report.

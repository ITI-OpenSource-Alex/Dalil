# 05 — Landing Page Components

## Objective

Replace the four placeholder landing-page components (`Features`,
`HowItWorks`, `Pricing`, `Footer`) with real, styled sections that match the
existing Hero/Navbar visual language, so `/` reads as a finished product
page rather than degrading into raw browser-default headings.

## Background

`/` is the first screen any reviewer sees. Below a genuinely polished Hero
section (`Hero.tsx`, `HeroChat.tsx`, `HeroContent.tsx`) and a real Navbar,
the page currently collapses into four one-line placeholder components:

```
Features.tsx    → <h1>features</h1>
HowItWorks.tsx  → <h1>Howitworks</h1>
Pricing.tsx     → <h1>pricing</h1>
Footer.tsx      → <h1>footer</h1>
```

This was confirmed identical across `dev` and every other feature branch —
there is no earlier, complete version of these components to recover; they
must be built from scratch.

Additionally, `Navbar.tsx` links to `#how-it-works`, `#features`, and
`#pricing` anchors that don't currently exist anywhere on the page, so even
the working navbar's in-page links currently no-op.

## Why This Matters

This single defect likely costs more perceived quality than every other
item in this plan combined, and it is the cheapest fix available: pure
presentational markup, zero API calls, zero state, zero integration risk
with any authenticated flow. It is the highest visual return per
engineering hour anywhere in this codebase.

## Scope

**In scope:**
- Full implementations of `Features`, `HowItWorks`, `Pricing`, `Footer`.
- Section `id` attributes matching the Navbar's existing anchor targets,
  plus smooth-scroll behavior.
- Responsive behavior at 375px, 768px, and 1440px.
- Minor `layout.tsx` metadata additions (OpenGraph fields) while already in
  that area of the codebase.

**Out of scope:**
- A real `/pricing` route (tracked separately in Phase 2 — this task only
  builds the reusable `Pricing` component and section, not a standalone
  route).
- Any Stripe/billing integration — the Pricing section is presentational
  only; its CTA points at `/register` for now.
- Redesigning the Hero, HeroChat, or Navbar, which are already complete.

## Files Expected to Change

```
services/frontend/components/landing/Features.tsx
services/frontend/components/landing/HowItWorks.tsx
services/frontend/components/landing/Pricing.tsx
services/frontend/components/landing/Footer.tsx
services/frontend/app/page.tsx
services/frontend/components/landing/Navbar.tsx
services/frontend/app/layout.tsx
```

## Detailed Implementation Plan

Do not invent a new visual language. `Hero`, `HeroChat`, `HeroContent`, and
`Navbar` already establish a consistent one: emerald-700 as the primary
color, slate neutrals, `rounded-2xl`/`rounded-3xl` cards,
`border-slate-200`, generous vertical rhythm (`py-24`-scale spacing), and a
`max-w-7xl` centered container. Every new section must read as a
continuation of that page, not a bolted-on addition.

**`Features`** — three cards matching the UI requirements spec: Opportunity
Matching, IELTS Preparation, CV Review. Each card: an icon (lucide-react is
already a project dependency), a heading, and a two-line body. Responsive
grid: `grid-cols-1` on mobile, `md:grid-cols-3` on larger screens. Be
careful with copy honesty — CV Review is not currently a reachable feature
in the product, so describe it as a platform capability without implying a
reviewer can click through and use it today.

**`HowItWorks`** — four numbered steps: create profile → get matched →
generate checklist → practise IELTS. Numbered circles in the emerald
palette, with connecting rules between them on desktop and a stacked layout
on mobile. This section should be written so its four steps mirror the
actual demo script's narrative arc — the page and the presenter should tell
the same story.

**`Pricing`** — a Free vs. Paid comparison. The Free column must list what
the demo actually demonstrates: opportunity matching, application
checklists, chat Q&A. The Paid column: IELTS exam simulations, speaking
practice, writing evaluation, CV review — at $7/month per the UI
requirements spec. Prefer a two-column card layout over a data table; it
renders faster to build and sidesteps responsive-table complexity entirely.
Include a CTA button pointing at `/register` (a dedicated `/pricing` route
is intentionally deferred to a later, cheap follow-up task once this
component exists).

**`Footer`** — three or four link columns (e.g. Product / Company / Legal),
a logo mark reusing the Navbar's existing treatment, and a copyright line.
Footer links may legitimately point at `#` for now — a footer is the one
place in the application where placeholder links are a normal, expected
convention and will not read as broken, unlike the sidebar (see
[06 — Sidebar Navigation Cleanup](06-sidebar-navigation.md), where the same
pattern is a real defect).

**Anchor wiring.** `Navbar` already links to `#how-it-works`, `#features`,
and `#pricing`. Add matching `id` attributes to each new section's wrapper
(either within the component itself or on its wrapper in `page.tsx`), and
enable smooth-scroll behavior (`scroll-behavior: smooth` at the appropriate
CSS scope). This is a very small addition that makes the navbar
demonstrably functional rather than a decorative row of dead links.

**Metadata.** While already editing `layout.tsx`, add `og:image` and
confirm the meta description are set per the spec's non-functional
requirement for the landing page — title and a base description already
exist; OpenGraph fields are a small, low-risk addition worth making while
in this area.

## Edge Cases

- Verify at all three target breakpoints (375px, 768px, 1440px) explicitly
  — `Hero` uses `lg:grid-cols-2`, so the mid-range 768px breakpoint is the
  least-exercised region of the existing layout and the most likely place
  for a new section to introduce horizontal overflow.
- Heading hierarchy: ensure exactly one `h1` remains on the page (in Hero)
  and that new sections use `h2`/`h3` appropriately — this affects both
  accessibility and the Lighthouse a11y score target.
- Confirm the existing `test/seo/lighthouse.spec.ts` suite is re-run after
  this change rather than assumed to still pass — real semantic sections
  should improve the score, but this must be verified, not assumed.

## Acceptance Criteria

- No component under `components/landing/` returns a bare placeholder
  heading.
- All four new sections render correctly at 375px, 768px, and 1440px with
  no horizontal page scroll introduced.
- All three Navbar in-page anchor links (`#how-it-works`, `#features`,
  `#pricing`) scroll smoothly to their correct matching sections.
- Lighthouse accessibility score on `/` remains above 90 (the existing
  non-functional requirement).
- `next build` succeeds and `/` remains statically prerendered (shown as
  `○` in the build route summary, unchanged from current behavior).

## Verification Steps

1. `npm run build && npm start`; open `/`.
2. Scroll the full page top to bottom; confirm a continuous, visually
   consistent treatment from the Hero through the new Footer.
3. Click each of the three Navbar in-page links in turn; confirm smooth
   scroll to the correct section each time.
4. Resize the browser through all three target breakpoints; confirm no
   horizontal overflow and no clipped or overlapping text at any of them.
5. Run the existing Lighthouse spec (`test/seo/lighthouse.spec.ts`);
   confirm the accessibility score remains above 90.

## Dependencies

None. Fully independent of every other task in this plan — pure
presentational work with no shared state or API surface.

## Estimated Effort

2.5 hours.

## Risk

**Very Low.** Four leaf components with no props, no data fetching, and no
shared state. Cannot affect any authenticated flow or any other page in the
application.

## Status

Completed. `Features.tsx`, `HowItWorks.tsx`, `Pricing.tsx`, `Footer.tsx`
fully implemented in the established Hero/Navbar visual language; section
`id`s added matching the Navbar's anchors; `scroll-behavior: smooth` added
to `globals.css`; OpenGraph/Twitter metadata plus a `metadataBase` and a
new `public/og-image.svg` added to `layout.tsx` (the `metadataBase`
addition wasn't explicitly named in the plan but was required — without it
Next's build emitted a warning that the image URLs couldn't be resolved to
absolute URLs at all). Verified: `next build` succeeds, `/` remains
statically prerendered (`○`), production server + real headless-browser
checks confirm no stray placeholder `<h1>`, exactly one `<h1>` on the page,
all three Navbar anchors scroll their target section into view, no
horizontal overflow at 375px/768px/1440px, and the existing
`test/seo/lighthouse.spec.ts` accessibility audit passes at **92** (> 90
threshold) — run via a temporary one-off Playwright config since
`playwright.config.ts`'s `testDir` doesn't cover `test/seo/` and no npm
script exists for it (temp config deleted after use, not part of the
change).

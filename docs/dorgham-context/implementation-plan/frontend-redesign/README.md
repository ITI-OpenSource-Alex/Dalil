# GOA Frontend Redesign — Implementation Plan

**Scope:** `services/frontend` only (plus one narrow, explicitly-authorized Gateway routing addition in Phase 3 — see [phase-3-auth-onboarding.md](phase-3-auth-onboarding.md)).
**Status:** Phases 0–4 complete. Phases 5–6 planned, not started.
**Origin document:** [`docs/FRONTEND-REDESIGN-PLAN.md`](../../../FRONTEND-REDESIGN-PLAN.md) — the original audit and proposal this whole effort was scoped from. That document stays as the historical record of the audit findings and the reasoning behind the token/component architecture; this folder tracks execution against it, phase by phase, and is the one to read for "what actually happened" and "what's next."

---

## Overall redesign vision

GOA is a high-stakes product — people make decisions about their education and money on it. Before this effort, the product read as developer-built: three different visual languages depending on which surface a user was on (marketing used `slate-*` neutrals and `emerald-700`; the authenticated app shell used `gray-*` and raw hex `#0d4d3a`; chat and speaking used a third, bespoke green-gray palette), the entire app rendered in Arial because a stray CSS rule silently overrode the loaded web font, and there was no shared component library — the same button was hand-rolled with drifting padding and radius in eight different files.

The vision is a single product with one visual language end to end: a user moving from the landing page through registration, onboarding, and into the authenticated app should never be able to tell where a page was "redesigned" and where it wasn't, because eventually there is no unredesigned surface left. The tone is *calm, editorial, and credible* — not *playful SaaS* — because the product's job is to be trusted with someone's education and money.

## Design principles

In priority order (unchanged since the original plan, restated here because every phase is graded against them):

1. **One product, one surface.** Marketing and the authenticated app share the same tokens, neutrals, brand green, radius, and elevation rules. The app is allowed to be denser than marketing; it is not allowed to be a different design.
2. **Tokens are the only source of color.** A raw hex literal or a bare `gray-400` in `components/` or `app/` is a defect, not a style choice. This is enforced by an automated test ([`test/unit/ui-server-boundary.test.ts`](../../../../services/frontend/test/unit/ui-server-boundary.test.ts)'s "design token discipline" suite), not just convention.
3. **Hierarchy through type and space, not through borders.** Replace border-boxing-everything with a real type scale, generous vertical rhythm, and a two-tier elevation model.
4. **Server-first.** The landing page stays fully static. Motion and interactivity are added at the leaf, in small client components — never by making a whole section `"use client"`.

## Design system philosophy

- **Two-layer token architecture.** Layer 1 (`@theme`) holds raw primitive ramps (`forest-*`, `sand-*`, `sage-*`) that components never reference directly. Layer 2 (semantic aliases like `--canvas`, `--surface`, `--brand`, `--fg-muted`) is what components actually consume, defined once under `:root` and mirrored under a dark-mode block so a future theme toggle costs zero component changes. Full reference: [`docs/DESIGN-TOKENS.md`](../../../DESIGN-TOKENS.md).
- **Primitives own no product knowledge.** `components/ui/*` takes props and renders; it never imports from `lib/*-api.ts` and never fetches. Domain components compose primitives — they don't write raw Tailwind color utilities.
- **Accessibility is structural, not a pass at the end.** The `Field` primitive wires `aria-describedby`/`aria-invalid`/`role="alert"` automatically, so every form built on it is correct by construction rather than by a reviewer remembering to add it.
- **Motion is for orientation and feedback, never decoration**, with a global `prefers-reduced-motion` kill switch (CSS) plus `useReducedMotion()` (framer-motion) — both halves are required because CSS transitions and framer-motion's inline-style animations aren't caught by the same mechanism.
- **Enforcement over convention.** Where the original audit found a rule being violated by habit (raw hex colors, `gray-*`/`slate-*` ramps, an untested boundary between server- and client-rendered primitives), the fix ships with an automated test that fails the build if the violation returns — not just a written rule someone has to remember.

## Progress tracker

| Phase | Name | Status | Doc |
|---|---|---|---|
| 0 | Foundation (tokens, fonts, `cn`/`motion` libs) | ✅ Complete | [phase-0-foundation.md](phase-0-foundation.md) |
| 1 | Design system primitives | ✅ Complete | [phase-1-design-system.md](phase-1-design-system.md) |
| 2 | Landing page redesign | ✅ Complete | [phase-2-landing-page.md](phase-2-landing-page.md) |
| 3 | Auth + Onboarding | ✅ Complete | [phase-3-auth-onboarding.md](phase-3-auth-onboarding.md) |
| 4 | Authenticated app shell | ✅ Complete | [phase-4-app-shell.md](phase-4-app-shell.md) |
| 5 | Exams, chat & practice surfaces + states | 📋 Planned, not started | [phase-5-exams.md](phase-5-exams.md) |
| 6 | Checklist, profile, and final polish sweep | 📋 Planned, not started | [phase-6-polish.md](phase-6-polish.md) |

## Current status

As of this writing, every pre-authentication and app-shell surface is on the design system: the landing page, the full auth journey (register/login/forgot-password/reset-password/verify-email), the onboarding wizard, and the authenticated app's chrome (sidebar, shared layout, page containers, user menu). `components/ui/` contains 20 primitives, each covered by the server/client-boundary and token-discipline test suite. `vitest run` passes 198/198 tests; `tsc --noEmit` and `npm run build` are clean.

**Not yet redesigned:** the content *inside* chat, exam (hub/shell/results), reading, writing, and speaking pages still carries the pre-redesign visual language in places (raw hex, `gray-*`, bespoke palettes) — Phase 4 unified the chrome around these pages (sidebar, layout, page containers) but explicitly did not touch their internal content, which was out of that phase's scope. Checklist and profile got light token cleanup as part of the Phase 4 file moves but not a full redesign pass. These are exactly what Phases 5–6 cover.

## Remaining phases — high-level roadmap

**Phase 5 — Exams, chat & practice surfaces, and states.** Full token migration of the exam hub, exam shell (timer/header chrome), exam results, reading/writing/speaking runtimes, and chat. Introduces the `EmptyState` pattern and route-level `loading.tsx` skeletons app-wide, and consolidates the app's error banners onto `Alert`. This is the largest remaining phase because it's the core product surface.

**Phase 6 — Checklist, profile, and polish sweep.** Full redesign of the checklist (timeline treatment) and profile (section cards, completeness meter) pages, designed empty/coming-soon states for the not-yet-built Opportunities/Dashboard/CV-Review nav entries, then a cross-cutting polish pass: motion audit with reduced-motion verification, full contrast audit, keyboard walkthrough of every flow, responsive pass at 320/375/768/1024/1440, and Lighthouse gates extended across all authenticated routes.

Each phase is independently shippable and leaves the app in a fully working state — there is no big-bang rewrite step anywhere in this plan.

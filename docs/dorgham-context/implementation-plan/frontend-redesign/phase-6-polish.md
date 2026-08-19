# Phase 6 — Checklist, Profile, and Polish Sweep

**Status:** 📋 Planned, not started.

This is a forward-looking implementation plan, written so a new engineer can execute it without needing the rest of this conversation for context. It assumes Phases 0–5 are complete — every product surface is on the design system, every route has a designed loading/empty/error state, and the token-discipline test covers the entire `app/`/`components/` tree.

## Goal

Two distinct halves. First, finish the two remaining un-redesigned content surfaces (checklist, profile) and give the not-yet-built nav entries (Opportunities, Checklists index, CV Review) a designed placeholder instead of an inert "Soon" chip pointing nowhere. Second, run the cross-cutting polish sweep the origin plan reserves for last precisely because it's only meaningful once every other surface already exists on the system: motion audit, contrast audit, full keyboard walkthrough, responsive pass at fixed breakpoints, and flipping the token-discipline enforcement from a passive test to a hard gate if it isn't already one.

## Scope

- `components/checklist/*` (`ChecklistItemRow`, `ChecklistProgress`, `ChecklistView`, `FinancialRequirements`, `PhaseSection`, `PrintButton`) and `app/(app)/checklist/[programId]/page.tsx`
- `app/(app)/profile/page.tsx` and any profile-specific components
- Designed empty/coming-soon states for `Opportunities`, `Checklists` (index — only `/checklist/[programId]` exists today, no list view), and `CV Review` nav entries
- App-wide polish: motion, contrast, keyboard, responsive, Lighthouse, lint enforcement

Out of scope: building the actual Opportunities or Dashboard features (the origin plan is explicit — §0.8: "these are treated in this plan as design-system-ready shells and empty states, not as new features... out of scope"). This phase ships the *shell* those features will eventually live in, not the features themselves.

## Checklist redesign

Current state (per the origin plan §8 and Phase 4's light-touch pass): `/checklist/[programId]` only — no index page. Phase 4 tokenized the page's outer wrapper (`PageContainer`, `Badge`, `Heading`) but the origin plan's fuller vision — "restyle phases as a vertical timeline with progress; item rows on `Checkbox`; preserve the print rules exactly; add an index/empty state" — has not been executed.

- **Timeline treatment**: `PhaseSection` becomes a vertical timeline with `ChecklistProgress` driving a visual progress indicator per phase (likely built on the `Progress` primitive, or a bespoke timeline component composed from `Card`/`Badge` if `Progress`'s linear-bar shape doesn't fit a multi-phase timeline — decide during implementation which fits better rather than forcing `Progress` into a shape it wasn't designed for).
- **Item rows on `Checkbox`**: `ChecklistItemRow` should use the Phase 1 `Checkbox` primitive rather than any hand-rolled checkbox markup — verify current implementation before assuming it needs replacing.
- **Print rules preserved exactly**: `PrintButton.tsx` and the `print-hidden`/`print:no-underline` CSS rules in `FinancialRequirements.tsx` and `ChecklistView.tsx` are load-bearing product behavior (a user genuinely prints their checklist) — Phase 4 already proved this pattern works by moving the sidebar's print-hiding onto `print:hidden` on the sidebar itself; this phase should audit whether any *other* chrome (the new `PageContainer`, any new timeline UI) also needs `print:hidden`/`print:` treatment, and verify a real print preview (not just visual inspection) before calling this done.
- **Index/empty state (new)**: no `/checklist` index route exists today. Build one — a list of the user's checklists (if the backend supports listing; confirm the actual API surface in `lib/checklist-api.ts` before assuming an endpoint exists) or, if no multi-checklist listing endpoint exists on the backend, a single empty/coming-soon state explaining how a checklist gets created, consistent with how the CV Review/Opportunities placeholders are handled below. **Do not fabricate a backend capability that doesn't exist** — if listing isn't supported, the honest move (matching this project's established pattern from Phase 3's onboarding-schema-gap disclosure) is a clearly-labeled single-checklist view with a note about what's not yet available, not a fake list.

## Profile redesign

Current state: Phase 4 replaced the raw-hex banners/cards with `Alert`/`Card`/`Badge`, but the page structure itself — a two-column `dl` grid of account + application-profile fields — was not restructured, per the origin plan's fuller vision: "section cards, avatar, completeness meter, edit affordances (UI only)."

- **Avatar**: the Phase 4 sidebar's `initialsFromEmail()` avatar-badge logic already exists and could be extracted into a small shared piece (or just visually echoed) rather than reinvented — profile is a natural place for a larger version of the same avatar treatment.
- **Completeness meter**: a `Progress`-based indicator showing how many of the `UpdateProfileDto` fields (degree level, GPA, IELTS score, field of study, ECTS, work experience, target countries — see [phase-3-auth-onboarding.md](phase-3-auth-onboarding.md) for the full field list and its documented gaps) are actually filled in. This directly surfaces the Phase 3 finding that several onboarding-collected fields (university, graduation year, target degree/major/intake) have nowhere to be saved — the completeness meter should only count fields the backend DTO actually supports, not silently imply 100% when data the user entered was never persisted.
- **Edit affordances, UI only**: per the origin plan, this phase builds the *UI* for editing (form fields, save button) — whether it wires to a real mutation depends on what `PUT /api/profile` (added in Phase 3) already supports. Since that endpoint already exists and is already called by onboarding, wiring profile's edit form to the same `authApi.updateProfile()` call is likely in-scope as "using an existing endpoint," consistent with how Phase 3 treated `forgot-password` and Phase 4 treated `auth/logout` — reusing something that already exists is not new backend scope. Confirm this reasoning holds before implementing (i.e., don't add or change backend validation — only call the existing endpoint from a new UI surface).

## Coming-soon / empty-state shells for unbuilt features

The sidebar (Phase 4) already renders `Opportunities`, `Checklists`, and `CV Review` as inert `href: null` "Soon" badges — this phase does **not** change that inert-nav-entry behavior (still correctly out of scope to build the real features), but per the origin plan §8, should give each a real route with a designed `EmptyState` so a determined user who somehow lands on the URL (or a future engineer building the real feature) has a starting shell rather than a 404. Use the `EmptyState` primitive from Phase 1 for each. This is intentionally minimal — a heading, an explanatory sentence, and (optionally) an expected-availability note — not a feature implementation.

## Cross-cutting polish sweep

**Motion audit.** Walk every animated surface built across Phases 2–5 and confirm: (a) it uses `lib/motion.ts`'s shared `DURATION`/`EASE`/variant exports rather than inline literals, (b) every framer-motion animation involving movement has a `useReducedMotion()`-gated fallback via the `reduced()` helper, (c) no bare `transition` (all-properties) classes remain anywhere — grep for `className.*"transition"` without a following `-` (e.g., `transition-colors`) as a starting heuristic, since a bare `transition` animates layout properties at the browser default and was called out in the origin audit (§0.5) as the dominant, unguarded pattern before this whole effort started.

**Contrast audit.** Every semantic token pair should be verified against its actual usage, not just assumed correct because it's a token — `docs/DESIGN-TOKENS.md` documents the *intended* contrast ratios (`fg` 15.9:1, `fg-muted` 8.3:1, `fg-subtle` 6.0:1, all on white/`surface`), but real usage can still combine tokens in unintended ways (e.g., `fg-subtle` on `canvas-subtle` rather than `surface` may not hit the same ratio — verify, don't assume the documented number transfers to every combination).

**Keyboard walkthrough.** Manually tab through every flow end to end: landing → register → login → onboarding → chat → exam (hub → shell → results) → profile → checklist → logout. Confirm: every interactive element is reachable and operable by keyboard alone, focus order matches visual order, focus is never silently lost (especially after a modal closes, a wizard step advances, or a dropdown — like the Phase 4 user menu — closes), and no keyboard trap exists anywhere.

**Responsive pass at fixed breakpoints**: 320, 375, 768, 1024, 1440px, per the origin plan §10. Test every surface touched across all six phases at each width, not just the ones with a documented known issue — Phase 5's plan calls out specific known gaps (reading nav rail, exam shell mobile split, chat's fixed padding); this pass is the systematic sweep that catches what wasn't already flagged.

**Lighthouse gates extended app-wide.** `test/seo/lighthouse.spec.ts` currently gates only the landing page. Per the origin plan §11/§13, extend it to `/login`, `/chat`, and `/exam` at minimum, targeting accessibility ≥ 90 (matching the existing landing-page gate) and, where the origin plan's stretch targets apply, performance ≥ 90 / CLS < 0.1 / LCP < 2.5s. Confirm current gate scope in the actual test file before assuming what's already covered.

**Enforcement: flip token-discipline from warning to error, if not already.** The origin plan's §7.5/§14 describes the raw-hex/`gray-*` scan test as initially "scoped as a warning" during Phase 1, meant to become a hard failure once adoption is complete. Since Phases 1–5 (once Phase 5 ships) will have brought the entire `app/`/`components/` tree onto tokens, confirm the test in `test/unit/ui-server-boundary.test.ts` (or wherever the scan lives by this point) fails the build rather than warning, and that it covers the full tree — not just `components/ui/` as it does today per Phase 1's original scoping — since by this phase, page-level files should be equally held to the rule.

## Reusable components

No new `components/ui/*` primitives anticipated. If checklist's timeline treatment needs a genuinely new shape `Progress` doesn't cover, build it as a `components/checklist/` domain component composed from `Card`/`Badge`/`Progress` — not a new primitive, since a checklist timeline carries checklist-domain knowledge.

## Accessibility goals

- Profile's edit-affordance form (new in this phase) must use `Field` for every input, inheriting the `aria-describedby`/`aria-invalid`/`role="alert"` wiring automatically — the same discipline every form since Phase 3 has followed.
- Checklist's timeline/progress UI must expose progress via `aria-valuenow`/`aria-valuemax` (via the `Progress` primitive or equivalent ARIA if a bespoke timeline is built) — not a purely visual indicator, matching the precedent set by the Phase 3 onboarding stepper.
- The full keyboard walkthrough (above) *is* an accessibility goal for this phase, not just a QA step — treat any focus-order or keyboard-trap finding as a defect to fix before calling the phase done, not a follow-up ticket.

## Responsive behavior

- Profile's `grid-cols-2` field layout (flagged in the origin plan §10 as "cramped on small screens... unconditional") should collapse to a single column below a defined breakpoint.
- Checklist timeline needs an explicit mobile treatment — a vertical timeline is naturally more mobile-friendly than the current two-column layout it may replace, but verify at 320/375px specifically since timelines with wide connector graphics can still overflow.
- Coming-soon/`EmptyState` shells should be verified responsive by construction (the `EmptyState` primitive should already handle this if built correctly in Phase 1 — this is a verification task, not new work).

## Verification strategy

1. `npx tsc --noEmit`, `npm run build`, `npx vitest run` clean — the same baseline every phase has held.
2. `test/unit/checklist-components.test.tsx`, `checklist-estimate.test.ts`, `checklist-phases.test.ts` should continue passing unmodified unless checklist markup/copy this phase changes requires updates, in which case update in the same commit.
3. `test/e2e/checklist.spec.ts` — review for selector/copy coupling before changing checklist markup, per the same discipline as every prior phase.
4. Manual Playwright screenshots at all five fixed breakpoints (320/375/768/1024/1440) for checklist, profile, and each coming-soon shell.
5. Full Lighthouse run across the newly-gated routes; record actual scores in this document (or a linked report) once achieved, rather than only asserting a threshold in CI.
6. A literal, tracked keyboard walkthrough — recommend recording it as a checklist in this file's own future revision (or a linked QA doc) so "we did a keyboard pass" is falsifiable rather than asserted.

## Acceptance criteria

- Checklist has a timeline-style phase view, `Checkbox`-based item rows, a working index/empty state, and print output verified unchanged from before this phase (checklist's print behavior is the one feature in this entire redesign effort with a hard "must not regress" bar, since it's real user-facing functionality, not just visual chrome).
- Profile has section cards, an avatar, a completeness meter that only counts backend-persistable fields, and a working edit form wired to the existing `PUT /api/profile` endpoint (no new backend endpoint or validation change).
- Opportunities, Checklists-index (if not otherwise resolved by the checklist work above), and CV Review each have a real route rendering a designed `EmptyState` rather than remaining unreachable "Soon" chips with no destination.
- No bare (all-properties) `transition` classes remain anywhere in `app/`/`components/`.
- Every framer-motion animation with movement has a verified `useReducedMotion()` fallback.
- Lighthouse accessibility ≥ 90 holds on `/`, `/login`, `/chat`, and `/exam`.
- The token-discipline scan runs as a hard failure (not a warning) across the full `app/`/`components/` tree.
- A completed, documented keyboard walkthrough of the full user journey with zero unresolved traps or lost-focus findings.

## Definition of done for the overall frontend redesign effort

Once Phase 6 is complete, the README.md progress tracker in this folder should be updated to mark all phases complete, and this documentation set becomes the durable record of the effort — at that point, consider whether `docs/FRONTEND-REDESIGN-PLAN.md` (the original proposal) should be marked superseded/archived in favor of this phase-by-phase record, since the proposal's "Status: Proposal, not yet implemented" header will no longer be accurate.

# Phase 0 — Foundation

**Status:** ✅ Complete
**Note on provenance:** this phase (and Phases 1–2) executed before the conversation this documentation set was written from began — reconstructed here from the current repository state, [`docs/FRONTEND-REDESIGN-PLAN.md`](../../../FRONTEND-REDESIGN-PLAN.md) §0/§3/§4/§14, and [`docs/DESIGN-TOKENS.md`](../../../DESIGN-TOKENS.md). Phases 3–4 (documented in their own files) were executed with full first-hand detail.

## Goal

Fix the two defects making the entire application look unfinished before any component work starts, and lay the infrastructure every later phase depends on: a real token system, a class-merging utility, and a shared motion vocabulary. No intended visual redesign in this phase beyond the font fix and whatever the token migration itself changes.

## Scope

- `app/globals.css` — full rewrite onto a two-layer token architecture.
- `app/layout.tsx` — font loading fix.
- `lib/cn.ts` (new) — `clsx` + `tailwind-merge` composition helper.
- `lib/motion.ts` (new) — shared framer-motion duration/easing/variant vocabulary.
- New dependencies: `clsx`, `tailwind-merge` (already present in `package.json`; `lucide-react` and `framer-motion` were pre-existing).
- Explicitly **not** in scope: any component in `components/ui/`, any page content. This phase is infrastructure only.

## The defects this phase fixes

Documented in full in the origin plan §0.2; summarized here because they're the reason this phase exists:

1. **`body { font-family: Arial, Helvetica, sans-serif }`** in the old `globals.css` silently overrode the Geist font `layout.tsx` loads via `next/font` — the entire application rendered in Arial, with the `--font-geist-sans` variable wired into `@theme inline` and then discarded.
2. **Two `:root` blocks** in the old file, the second redeclaring `--background`/`--foreground` and sitting between the first block and the `prefers-color-scheme: dark` media query — dark mode was structurally dead regardless of the OS preference.
3. **Six semantic-sounding custom properties** (`--primary`, `--secondary`, `--success`, `--warning`, `--danger`, `--border`) were declared but never mapped into `@theme`, so no Tailwind utility could reach them — every component hardcoded colors instead of using them.
4. **`html { scroll-behavior: smooth }`** was unconditional, with no `prefers-reduced-motion` escape.

## Architecture decisions

**Two-layer token model.** Layer 1 (`@theme`) holds three primitive color ramps — `forest-*` (brand, anchored on the pre-existing `#0d4d3a`), `sand-*` (accent, warm amber), `sage-*` (the single neutral ramp, faintly green-tinted so it doesn't fight the brand) — plus type, radius, elevation, and motion scales. Layer 2 (`:root` / `[data-theme="dark"]`) holds semantic aliases (`--canvas`, `--surface`, `--border`, `--fg-muted`, `--brand`, `--focus-ring`, etc.) that re-point to Layer 1 values. A `@theme inline` block maps Layer 2 onto Tailwind utility names, so `bg-canvas`, `text-fg-muted`, `border-border` work as ordinary Tailwind classes.

**Why two layers instead of one:** components must never reference `forest-600` or `sage-200` directly except as a documented one-off escape hatch. Because Layer 2 is what components actually consume, a dark theme is a matter of adding a `data-theme` toggle and filling in the already-authored dark values under `[data-theme="dark"]` — zero component changes required later. The dark values are authored now (in `globals.css`) specifically so they don't rot unused and undiscovered.

**Radius by role, not by size.** Four values, each with an assigned job, replacing six ad hoc values used with no rule: `--radius-chip` (6px — badges, tags), `--radius-control` (10px — buttons, inputs), `--radius-card` (16px — cards, panels, alerts), `--radius-panel` (24px — hero surfaces, modals, marketing).

**Elevation as a four-level named scale** (`--shadow-e1`…`e4`), forest-tinted rather than pure black — untinted black shadows on a warm canvas read as cheap. `e0` (no shadow) is deliberately not a token: the default separator between surfaces is a border, not a shadow.

**Motion tokens mirrored in two places.** `--duration-fast/base/slow/slower` and `--ease-out/in-out/spring` live in `globals.css` for CSS transitions, and are mirrored in seconds (framer-motion's unit) in the new `lib/motion.ts`, which also exports pre-built `Variants` (`fadeIn`, `fadeUp`, `scaleIn`, `slideInRight`), a `stagger()` helper, and a `reduced()` helper that strips movement from a variant set when `prefersReduced` is true — because the CSS-level reduced-motion kill switch doesn't reach framer-motion's inline-style animations; that needs its own opt-in per animated component via `useReducedMotion()`.

## UI/UX decisions

- **Brand color:** consolidated on the deep forest green (`forest-800` = `#0d4d3a`, already used in 49 places pre-redesign) over the marketing pages' `emerald-700`. Rationale: ~9.8:1 contrast against white (comfortably AAA) versus emerald-700's borderline ~4.9:1, and more distinctive than default-Tailwind emerald.
- **Serif display type kept and formalized**, not dropped. The pre-existing app-shell instinct toward `font-serif` headings was judged a genuine asset (it's what gives the product an editorial voice rather than a dashboard voice) — Fraunces was added as a variable font on the weight axis only (other axes — SOFT, WONK, opsz — left at defaults to avoid inflating the font file for unused range), loaded via `next/font` with `display: swap`.
- **Reduced-motion is a global, unconditional kill switch** in `globals.css` (forces `scroll-behavior: auto` and near-zero transition/animation durations under `prefers-reduced-motion: reduce`), not an opt-in per component for the CSS half of the system.

## Components introduced

None — this phase is infrastructure. `lib/cn.ts` and `lib/motion.ts` are libraries, not UI components.

## Files created

- `services/frontend/lib/cn.ts`
- `services/frontend/lib/motion.ts`
- `docs/DESIGN-TOKENS.md` (token reference documentation)

## Files modified

- `services/frontend/app/globals.css` (full rewrite)
- `services/frontend/app/layout.tsx` (font loading — added Fraunces, fixed the Arial override via the `globals.css` rewrite, added a skip-to-content link as part of the same pass since it lives in the base layout)
- `services/frontend/package.json` / `package-lock.json` (`clsx`, `tailwind-merge` added)

## Accessibility improvements

- Global `prefers-reduced-motion` handling added where none existed before.
- A `:focus-visible` global ring token (`--focus-ring`) established as the one source of focus-ring styling, replacing the pre-existing mix of default outlines and ad hoc custom rings.
- Skip-to-content link added to the root layout (`app/layout.tsx`), targeting `id="main-content"` on each page's `<main>`.

## Performance improvements

- Restoring the Geist font (already downloaded via `next/font`, merely overridden) costs nothing — no new network request, no layout shift.
- Fraunces added as one additional `next/font` family, subset to latin, `display: swap`, so it never blocks text rendering.
- Token file itself adds negligible CSS weight (a few KB uncompressed, none of it per-component).

## Verification performed

No dedicated automated test suite exists for this phase specifically (the token-discipline test added in Phase 1 is what actually enforces it going forward — see [phase-1-design-system.md](phase-1-design-system.md)). Verified by: visual confirmation that the app renders in Geist/Fraunces rather than Arial, and that `npm run build`/`tsc --noEmit` remain clean after the `globals.css` rewrite.

## Screenshots

None captured specifically for this phase (no visual change was intended beyond the font correction). Visual confirmation of the token system in use is captured in the Phase 2–4 screenshot sets referenced in their respective docs.

## Lessons learned

- A single stray CSS rule (`body { font-family: Arial }`) had been silently discarding a correctly-configured `next/font` setup — the kind of defect that's invisible in a code review (the font loading code looks correct) and only surfaces by actually rendering the page. This is why later phases lean on real Playwright screenshots for verification rather than trusting that correct-looking code produces the correct-looking page.
- Authoring the dark-mode token values now, even though no toggle ships yet, is what keeps a "future feature" from silently rotting: if the values are never referenced they'd never be caught out of date. Since they're part of `globals.css`'s structure, adding a dark-mode toggle in a future phase is additive rather than another migration.

# GOA Design Tokens — Reference

Source of truth: [`services/frontend/app/globals.css`](../services/frontend/app/globals.css).
This document explains *when* to use each token. The CSS file is the *what*.

## The one rule

**Components use semantic tokens. Never raw hex, never `gray-*`/`slate-*`, and only rarely a primitive ramp step.**

```tsx
// ✗  before Phase 0 — three different greens, two neutral ramps, no meaning
<div className="border border-slate-200 bg-white text-gray-400" />
<button className="bg-[#0d4d3a] hover:bg-[#09382a]" />

// ✓  after
<div className="border border-border bg-surface text-fg-subtle" />
<button className="bg-brand hover:bg-brand-hover text-fg-on-brand" />
```

Primitive ramps (`forest-600`, `sage-200`, `sand-400`) exist as an escape hatch for a
deliberate one-off design decision. If you reach for one twice, it wants to be a
semantic token instead.

---

## Colour

### Primitive ramps

| Ramp | Role | Anchor |
|---|---|---|
| `forest-50…950` | Brand. Deep green. | `forest-800` = `#0d4d3a` |
| `sand-50…950` | Accent. Warm amber. | `sand-500` = `#de8e1b` |
| `sage-50…950` | The single neutral ramp, faintly green-tinted. | `sage-900` = `#1f2824` |

### Semantic tokens

**Surfaces** — back to front:

| Token | Use |
|---|---|
| `canvas` | Page background |
| `canvas-subtle` | Alternating sections, sidebars |
| `canvas-inset` | Wells, progress tracks, code blocks |
| `surface` | Cards, inputs, menus |
| `surface-raised` | Modals, popovers |
| `surface-inverse` | CTA bands, tooltips |

**Lines:** `border` (default hairline) · `border-strong` (emphasis, dividers under headers) · `border-inverse`

**Text** — all three pass WCAG AA on `surface` and `canvas`:

| Token | Contrast on white | Use |
|---|---|---|
| `fg` | 15.9:1 | Headings, primary body |
| `fg-muted` | 8.3:1 | Secondary body, descriptions |
| `fg-subtle` | 6.0:1 | Metadata, captions, placeholders |
| `fg-on-brand` | 9.8:1 on `brand` | Text on brand fills |
| `fg-inverse` / `fg-inverse-muted` | — | Text on `surface-inverse` |

> This retires `text-gray-400` (2.8:1), which **fails AA** and is currently used for
> metadata across profile, reading and chat.

**Brand:** `brand` · `brand-hover` · `brand-active` · `brand-subtle` (tinted bg) ·
`brand-muted` (icon tiles, chips) · `brand-border` · `brand-fg` (brand-coloured text)

**Accent:** `accent` · `accent-hover` · `accent-subtle` · `accent-border` · `accent-fg`
— one accent moment per view, on the single most important action or datum.

**Status** — each is a four-part set (`X` solid / `X-subtle` tint / `X-border` / `X-fg` text-on-tint):
`success` · `warning` · `danger` · `info`

> `success` is green despite the green brand because users expect it. It is reserved
> strictly for state feedback and **never** for branding or calls to action, which is
> what keeps the two readings apart.

**Focus:** `focus-ring`. Applied globally via `:focus-visible` in the base layer.
On inverse/brand surfaces, override the *colour* only: `focus-visible:outline-sand-300`.

---

## Radius — by role, not by size

| Token | Value | Use |
|---|---|---|
| `rounded-chip` | 6px | Badges, tags, inline markers |
| `rounded-control` | 10px | Buttons, inputs, selects, menu items |
| `rounded-card` | 16px | Cards, panels, alerts, popovers |
| `rounded-panel` | 24px | Hero surfaces, modals, marketing |
| `rounded-full` | — | Avatars and pills only |

Tailwind's numeric `rounded-sm/md/lg/xl` scale still exists and still works — it is
left untouched so existing markup renders unchanged. New and redesigned code uses
the role-named tokens above.

## Elevation

| Token | Use |
|---|---|
| *(none)* | Default. Separation comes from `border`, not shadow. |
| `shadow-e1` | Resting card |
| `shadow-e2` | Hover state, dropdowns |
| `shadow-e3` | Modals, hero showcase |
| `shadow-e4` | Rare — full-screen overlays |

Shadows are forest-tinted, not black. Untinted black over a warm canvas is what makes
a UI look cheap.

## Motion

Durations: `--duration-fast` 120ms · `--duration-base` 200ms · `--duration-slow` 320ms ·
`--duration-slower` 500ms. Easing: `ease-out` (house curve) · `ease-in-out` · `ease-spring`.

In TSX, import from [`lib/motion.ts`](../services/frontend/lib/motion.ts) rather than
writing literals: `DURATION`, `EASE`, `transitions`, `fadeIn`, `fadeUp`, `scaleIn`,
`slideInRight`, `stagger()`, `reduced()`, `inViewOnce`.

**Never use a bare `transition` class** — it animates *every* property including layout
ones. Name the property: `transition-colors`, `transition-shadow`, `transition-transform`.

**Reduced motion** is handled in two places, and both are required:
- CSS transitions/animations — global kill switch in `globals.css`.
- framer-motion — animates via inline style and ignores that switch. Use
  `useReducedMotion()` + `reduced(variants, prefersReduced)`.

## Z-index

`--z-dropdown` 1000 · `--z-sticky` 1100 · `--z-overlay` 1200 · `--z-modal` 1300 ·
`--z-toast` 1400. Consumed as `z-1000` … `z-1400`.

## Typography

`font-sans` — Geist, all UI.
`font-serif` — Fraunces, display headings only.
`font-mono` — Geist Mono.

Serif is **not** applied globally to `h1`–`h6`. It belongs at display sizes; this app has
several `<h2>`s that are 14px section labels, where a serif reads as a mistake rather
than as a voice. The `Heading` primitive (Phase 1) and the marketing sections opt in.

Tailwind's default size ramp (12/14/16/18/20/24/30/36/48/60/72) is kept — it is already
correct. The change that matters is *usage*: body copy moves to `text-base` (16px), and
`text-xs` is reserved for metadata and badges.

## Dark mode

Authored, **not activated**. Every semantic token has a `[data-theme="dark"]` value.
Because components only ever touch the semantic layer, enabling dark mode is a matter
of adding a toggle that sets `data-theme` on `<html>` — zero component changes.

The previous `prefers-color-scheme` block was removed: it darkened only the page
background while every component stayed light, which is worse than no dark mode at all.

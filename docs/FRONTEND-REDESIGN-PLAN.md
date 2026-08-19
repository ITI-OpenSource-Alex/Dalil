# GOA Frontend Redesign & Design System — Implementation Plan

**Status:** Proposal, not yet implemented.
**Scope:** `services/frontend` only. No backend or feature work.
**Stack in place:** Next 16.2.9 (App Router), React 19.2.4, Tailwind v4 (CSS-first), framer-motion 12, lucide-react, chart.js, Playwright + Vitest.

---

## 0. Audit — what the code actually shows

This plan is grounded in a read of all 13k lines under `app/`, `components/`, `lib/`. The findings below are the reason each phase exists.

### 0.1 Three competing visual languages

| Surface | Neutrals | Brand | Radius | Shadow | Headings |
|---|---|---|---|---|---|
| Landing + auth | `slate-*` | `emerald-700` | `xl` / `2xl` | `shadow-sm` | sans, bold |
| App shell (sidebar, profile, exam) | `gray-*` | `#0d4d3a` / `#09382a` on `#fbfbfa` | `2xl` / `full` | `shadow-2xs` | **`font-serif`** |
| Chat + speaking | custom green-grays `#1D291E`, `#526053`, `#E8ECE7`, `#F2F5F1` | `#0D3820` | `full` / `2xl` | none | sans |

Counted across the codebase: **~40 distinct raw hex literals**, `gray-*` 311 uses, `emerald-*` 216, `slate-*` 108. Two neutral ramps and three greens is the single biggest reason the product reads as developer-built. A user moving from `/` → `/login` → `/chat` → `/exam` crosses three different products.

### 0.2 `globals.css` is broken, not just thin

[globals.css](../services/frontend/app/globals.css) is 60 lines and contains three real defects:

1. **`body { font-family: Arial, Helvetica, sans-serif }` (line 32)** overrides the Geist font that `layout.tsx` loads via `next/font`. The entire application currently renders in Arial. The `--font-geist-sans` variable is wired into `@theme inline` and then discarded.
2. **Two `:root` blocks** (lines 10–13 and 35–47). The second redeclares `--background`/`--foreground`, which silently defeats the `prefers-color-scheme: dark` block at line 22 — it sits *between* them in source order, so dark mode is dead.
3. **`--primary`, `--secondary`, `--success`, `--warning`, `--danger`, `--border` are declared but never mapped into `@theme`**, so no Tailwind utility can reach them. They are decorative. Every component hardcodes instead.

Also: `html { scroll-behavior: smooth }` is unconditional, with no `prefers-reduced-motion` escape.

### 0.3 There is effectively no component library

`components/ui/` contains three files: `skeleton.tsx` (13 lines), `checkbox.tsx` (48), `sidebar.tsx` (397). There is **no Button, Input, Card, Badge, Modal, Alert, EmptyState, Field, Select, Textarea, Tabs, or Tooltip primitive.**

Consequence: the same submit button is hand-written in `LoginForm`, `RegisterForm`, `ResetPasswordForm`, `HeroButtons`, `Navbar`, `Pricing`, `ReadingExam`, `ChecklistView`, and every onboarding step — with drifting padding (`py-3` vs `py-3.5` vs `py-1.5`), radius (`rounded-xl` vs `rounded-full`), and color (`emerald-700` vs `#0d4d3a` vs `red-600`). The same input `className` string is copy-pasted verbatim 3× in `LoginForm` and `RegisterForm` alone.

No `cn()` helper, no `clsx`/`tailwind-merge`, no variant system.

### 0.4 No scales

- **Radius:** `rounded-full` 121, `2xl` 58, `xl` 48, `lg` 37, `3xl` 12, `md` 8 — six values, no rule about which means what.
- **Shadow:** `shadow-2xs` 28, `shadow-sm` 22, `xl` 4, `md` 3, `lg` 1 — no elevation model; `2xs` and `sm` are used interchangeably for the same card role on different pages.
- **Type:** `text-xs` 136, `text-sm` 158, `text-base` **7**. The application is almost entirely 12–14px. This is the second-biggest reason it reads as unpolished: no hierarchy, and body copy below comfortable reading size.

### 0.5 Motion is ad-hoc and unguarded

The dominant pattern is a bare `transition` class with no duration or easing token — the browser default (150ms, ease) applied to *all* properties, including layout ones. framer-motion appears in 15 files (all chat/speaking), each with inline literals like `duration: 0.4, delay: 0.15`. There is **no `prefers-reduced-motion` handling anywhere** in the codebase.

### 0.6 Accessibility gaps

Counts across `app/` + `components/`: `aria-describedby` **0**, `alt=` **1**, `sr-only` **3**, `aria-current` **1**, `focus-visible` 11 vs `focus:` 108, `aria-live` 2.

Concretely:
- Form errors in `LoginForm`/`RegisterForm`/`ResetPasswordForm` render as an unassociated `<p>` — not linked via `aria-describedby`, not `role="alert"`, and the invalid input carries no `aria-invalid`. A screen-reader user gets no announcement that submit failed.
- The Navbar mobile menu button ([Navbar.tsx:41](../services/frontend/components/landing/Navbar.tsx#L41)) has **no `onClick`, no `aria-label`, no `aria-expanded`** — it is a dead control. There is no mobile navigation on the landing page at all.
- No skip-to-content link.
- Focus rings are inconsistent; many interactive elements rely on the default outline while others use `outline-none` + a custom ring.

`test/seo/lighthouse.spec.ts` already gates landing-page accessibility at ≥ 90, so this work has a check to hold it.

### 0.7 Landing page structure

`app/page.tsx` is Navbar → Hero → Features → HowItWorks → Pricing → Footer. Observations:

- **Everything on the landing page is a Server Component** — zero client JS ships for `/`. This is a genuine asset and the redesign must preserve it.
- No social proof, no testimonials, no FAQ, no logo wall, **no closing CTA**. The page ends on a pricing table and drops straight into a thin footer.
- Conversion paths conflict: Navbar and Hero CTAs point to `/onboarding`; Pricing CTAs point to `/register`. Two different funnels for the same intent.
- `HeroStats` claims "95% Match Accuracy" and "120+ Universities" as bare numbers with no substantiation — a trust liability on a page whose job is trust.

### 0.8 Missing routes vs. requested scope

The request lists "Opportunity pages" and "Dashboard." Neither exists. `sidebar.tsx` renders Opportunities, Checklists, and CV Review as inert `href: null` "Soon" chips. Checklist exists only at `/checklist/[programId]` — there is no index. There are **no `loading.tsx` or `not-found.tsx` files anywhere**; only `app/error.tsx` and `app/exam/error.tsx`.

These are treated in this plan as *design-system-ready shells and empty states*, not as new features. Building the actual Opportunities and Dashboard pages is out of scope and flagged in §8.

### 0.9 Refactor risk

Playwright e2e uses `getByText` 23×, `getByRole` 19×, `data-testid` 18×. **Copy changes will break e2e tests.** Any section where I change wording must land with the corresponding spec update in the same commit. Class names are not asserted anywhere except one case in `essay-highlighter.test.tsx`, so restyling is safe; rewording is not.

---

## 1. Overall UI strategy

**Thesis:** GOA is a high-stakes product — people make decisions about their education and money on it. The visual language should read *calm, editorial, and credible*, not *playful SaaS*. The deep forest green already used in the app (`#0d4d3a`) is a better brand anchor than the generic `emerald-700`, and the existing serif-heading instinct in the app shell is worth keeping — but applied deliberately, not on three pages out of twelve.

Four principles, in priority order:

1. **One product, one surface.** Marketing and app share the same tokens, the same neutrals, the same brand green, the same radius and elevation rules. The app is allowed to be denser than marketing; it is not allowed to be a different design.
2. **Tokens are the only source of color.** After Phase 0, a raw hex or a bare `gray-400` in a component is a defect. Enforced by lint (§7.5).
3. **Hierarchy through type and space, not through borders.** The current UI leans on `border-slate-200` boxes to separate everything. Replace with a real type scale, generous vertical rhythm, and a two-tier elevation model.
4. **Server-first.** The landing page stays fully static. Motion and interactivity are added at the leaf, in small client components — never by making a section `"use client"` wholesale.

**Brand decision (recommended):** consolidate on the deep forest green as `brand`, with amber as `accent`. Retire `emerald-700` and all raw greens. Rationale: `#0d4d3a` has 49 existing uses, gives ~11:1 contrast on white (comfortably AAA, versus `emerald-700`'s ~4.9:1 which is borderline for anything but large text), and is more distinctive than the default-Tailwind emerald that reads as "unstyled bootstrap SaaS."

---

## 2. Design system architecture

```
services/frontend/
  app/
    globals.css              # @theme tokens + base layer ONLY. No component CSS.
  components/
    ui/                      # primitives — no product knowledge, no data fetching
      button.tsx             # variant/size via CVA-style map
      input.tsx  textarea.tsx  select.tsx
      field.tsx              # label + control + hint + error, wires aria-describedby
      card.tsx               # Card / CardHeader / CardBody / CardFooter
      badge.tsx
      modal.tsx              # focus trap, ESC, scroll lock, aria-modal
      alert.tsx              # info | success | warning | danger, role=status/alert
      skeleton.tsx           # (rewrite on tokens)
      empty-state.tsx
      spinner.tsx
      tabs.tsx
      tooltip.tsx            # wrap existing @radix-ui/react-tooltip
      checkbox.tsx  radio.tsx  switch.tsx
      progress.tsx
      icon.tsx               # single lucide wrapper enforcing size/stroke
      index.ts               # barrel
    layout/                  # app chrome
      app-shell.tsx  sidebar.tsx  topbar.tsx  page-header.tsx
    marketing/               # renamed from landing/
      navbar.tsx  hero/  features.tsx  how-it-works.tsx
      social-proof.tsx  faq.tsx  cta.tsx  footer.tsx
    <domain>/                # chat/, reading/, writing/, speaking/, checklist/ — unchanged locations
  lib/
    cn.ts                    # clsx + tailwind-merge
    motion.ts                # shared framer-motion variants + durations
```

**Rules:**
- `components/ui/*` may not import from `lib/*-api.ts`, may not fetch, may not know about GOA domain concepts. They take props and render.
- Domain components compose primitives; they do not write raw Tailwind color utilities.
- Two new dependencies: `clsx` + `tailwind-merge` (~3 kB combined, tree-shakeable). I'll implement variants with a plain typed lookup object rather than adding `class-variance-authority` — CVA buys little here and is another dep.

---

## 3. Theme / token architecture

Tailwind v4 is CSS-first, so tokens live in `globals.css`. Two layers:

**Layer 1 — primitives** (`@theme`): raw ramps. Never referenced directly by components.

```
--color-forest-50 … --color-forest-950     /* brand, anchored on #0d4d3a ≈ 800 */
--color-sand-50 … --color-sand-950         /* accent, amber family */
--color-stone-50 … --color-stone-950       /* the ONE neutral ramp, warm-tinted
                                              to match the existing #fbfbfa canvas */
--color-red-*  --color-green-*  --color-amber-*  --color-blue-*   /* status ramps */
```

**Layer 2 — semantic aliases** (`:root`, re-pointable): what components actually consume.

```
--color-bg            --color-bg-subtle      --color-bg-inset
--color-surface       --color-surface-raised
--color-border        --color-border-strong
--color-fg            --color-fg-muted       --color-fg-subtle    --color-fg-onBrand
--color-brand         --color-brand-hover    --color-brand-subtle  --color-brand-ring
--color-accent        --color-accent-subtle
--color-success / -subtle / -fg      --color-warning / …
--color-danger  / -subtle / -fg      --color-info    / …
--color-focus-ring
```

These are exposed to utilities via `@theme inline` so `bg-surface`, `text-fg-muted`, `border-border`, `ring-focus-ring` all work as normal Tailwind classes.

**Non-color scales** (also `@theme`):

- **Type:** `--text-xs` 12 / `--text-sm` 14 / `--text-base` 16 / `--text-lg` 18 / `--text-xl` 20 / `--text-2xl` 24 / `--text-3xl` 30 / `--text-4xl` 36 / `--text-5xl` 48 / `--text-6xl` 60 / `--text-7xl` 72, each with a paired line-height and tracking. Display sizes (4xl+) get `tracking-tight`; body gets `leading-relaxed`.
  Two families: `--font-sans` (Geist, restored) for UI, `--font-serif` for display headings — keeping the app shell's existing instinct but applying it consistently to page-level `h1`/`h2` across marketing *and* app.
- **Spacing:** 4px base. Restrict to a `1 2 3 4 6 8 12 16 20 24 32` step set; ban arbitrary values in review.
- **Radius:** collapse six values to four with assigned meaning — `--radius-sm` 6px (badges, chips, inline), `--radius-md` 10px (inputs, buttons), `--radius-lg` 16px (cards, panels), `--radius-xl` 24px (hero/marketing surfaces), plus `full` for avatars/pills only.
- **Elevation:** four levels — `--shadow-0` none (default; separation via `border`), `--shadow-1` resting card, `--shadow-2` hover / dropdown, `--shadow-3` modal / hero showcase. Tuned as low-alpha, large-blur shadows with a forest tint rather than pure black, which is what makes shadows look cheap.
- **Motion:** `--duration-fast` 120ms, `--duration-base` 200ms, `--duration-slow` 320ms, `--duration-slower` 500ms; `--ease-out` `cubic-bezier(.16,1,.3,1)`, `--ease-in-out`, `--ease-spring`.
- **Z-index:** named scale `dropdown 1000 / sticky 1100 / overlay 1200 / modal 1300 / toast 1400` — currently ad-hoc (`z-50`, `z-30`, `z-10`).

**Dark mode readiness (not shipped):** Layer 2 is defined once under `:root` and again under `[data-theme="dark"]` with the ramp steps inverted. Because components only ever touch Layer 2, enabling dark mode later is a matter of adding a `data-theme` toggle — zero component changes. The existing broken `prefers-color-scheme` block is deleted in Phase 0; a half-working dark mode is worse than none. I'll author the dark values as part of the token file so they don't rot, but leave the toggle unbuilt.

---

## 4. Global styling strategy

`globals.css` gets a defined structure and nothing else lives in it:

1. `@import "tailwindcss"`
2. `@theme` — primitive ramps + non-color scales
3. `:root` / `[data-theme="dark"]` — semantic aliases
4. `@theme inline` — semantic → utility mapping
5. `@layer base` — element defaults: `body` on `--font-sans` (**Arial override deleted**), `h1`–`h6` on the serif display family, `::selection`, `:focus-visible` global ring, `[hidden]`, form element resets
6. `@media (prefers-reduced-motion: reduce)` — global kill switch: `scroll-behavior: auto`, animation/transition durations forced to `0.01ms`
7. `@media print` — existing checklist rules, preserved verbatim

Duplicate `:root` blocks collapsed; unreachable `--primary`/`--secondary`/etc. removed in favour of the semantic layer.

---

## 5. Landing page redesign

New section order for `app/page.tsx`:

```
Navbar  →  Hero  →  Trust bar  →  Features  →  How It Works
        →  Proof (outcomes / testimonial)  →  Pricing  →  FAQ  →  CTA  →  Footer
```

The narrative arc: *hook → credibility → what it does → how it works → evidence → cost → objections → ask.* Today the page has hook, what, how, cost — and then stops. The three additions (Trust, Proof, FAQ) plus the closing CTA are what turn it from a feature list into a conversion page.

**Navbar** — keep sticky + blur; move to tokens; reduce height 80px → 64px (currently disproportionate); build the **working mobile menu** the current dead button implies (slide-over panel, focus trap, `aria-expanded`, ESC to close, body scroll lock — reusing the pattern already in `sidebar.tsx`); add scroll-state (transparent over hero → bordered + solid on scroll) as a tiny client leaf component.

**Hero** — stays structurally, as requested. Changes are polish only:
- Retire the `emerald-50 → white → orange-50` linear gradient for a subtler layered background: a soft forest radial glow, a faint grid or noise texture, and a clean white base. The current three-color gradient is the most "template" element on the page.
- Type: `h1` to the serif display family at `text-5xl`/`lg:text-7xl` with tightened tracking and a real `leading` value; the gradient-text span keeps the brand-to-accent sweep but on the new ramp.
- Spacing: `py-24` → responsive `py-20 lg:py-32`; grid gap 20 → 16 with a wider content column (the 50/50 split currently starves the headline).
- `HeroChat` mock: elevate to `--shadow-3`, add a browser-chrome frame and a subtle float/tilt, and **animate the three opportunity rows in on scroll** — this is the product demo and it currently sits inert.
- `HeroStats`: replace unsubstantiated "95% Match Accuracy" with claims that are defensible (e.g. programmes indexed, countries covered, skills assessed), and add count-up animation on view.
- **Fix the CTA split:** every primary CTA on the page routes to `/register`. `/onboarding` currently has no persistence (`handleFinish` in [onboarding/page.tsx:31](../services/frontend/app/onboarding/page.tsx#L31) is a stub that discards the wizard data) and sending cold traffic into it loses the user.

**Trust bar (new, small)** — a restrained row of destination-country flags / partner-institution names directly under the hero. Cheap to build, disproportionate credibility payoff. Must use real, honest content; placeholder logos would undercut the whole point.

**Features** — the three cards become a **bento grid**: one large card (Opportunity Matching, with an inline visual) spanning two columns, two standard cards beneath. Each gets a token-driven icon tile, a hover lift (`--shadow-1` → `--shadow-2`, 200ms), and a subtle brand-tinted top border. Add a fourth card for Checklists, which is a real shipped feature currently absent from the page.

**How It Works** — the four numbered circles with a hairline connector are the weakest section. Replace with an alternating two-column narrative: each step gets a real screenshot/mock on one side, copy on the other, alternating sides, with a scroll-linked progress rail down the centre. This is where storytelling lives.

**Proof (new)** — one strong testimonial or outcome stat block. If no real testimonials exist yet, ship this as an outcome-metrics band instead of fabricating quotes.

**Pricing** — keep two tiers. Improve: emphasise the Pro card with elevation and a brand-tinted surface rather than a `border-2` outline; align the two cards' feature lists on a shared baseline; add a billing-period toggle placeholder; add a "what happens after you hit the free limit" line. Move the "no card required" reassurance directly under the CTA button where it does work.

**FAQ (new)** — 5–6 accordion items handling the real objections: is it free, is the IELTS scoring accurate, what data do you store, which countries, how does matching work. Native `<details>`/`<summary>` styled with tokens — keeps the section server-rendered with zero JS.

**Footer** — currently thin. Expand to four columns + a newsletter/waitlist field, add social icons, add a language/region hint, restore proper `<h2 className="sr-only">` semantics, and populate the `href="#"` dead links (About, Contact, Privacy, Terms) or remove them. Dead links in a footer are a direct trust cost.

---

## 6. CTA section proposal

Placed between FAQ and Footer, full-bleed, and visually the heaviest moment on the page after the hero.

**Design:** full-width band on a deep forest surface (`--color-forest-900`) with a soft radial accent glow and low-opacity world-map or grid texture. Centred, max-width ~48rem:

- Eyebrow: small caps, accent color — *"Applications open now"*
- Headline: serif display, `text-4xl lg:text-5xl`, white — *"Your programme is out there. Let's go find it."*
- Sub: one sentence, `--color-forest-100`, restating the core value
- Primary button: high-contrast sand/white on forest, `--radius-md`, with arrow icon and a hover translate
- Secondary: ghost/outline — *"See how it works"* → `#how-it-works`
- Reassurance row beneath, small, with check icons: *Free forever tier · No card required · 2-minute setup*

**Motion:** whole block fades + rises 24px on entering the viewport, once, `--duration-slow` / `--ease-out`, respecting reduced-motion. Implemented as a single small client component so the rest of the page stays static.

**Accessibility:** forest-900 background against white text is ~14:1; the sand accent must be checked against forest-900 for the eyebrow (target ≥ 4.5:1) — verified during build, not assumed.

---

## 7. Component standardization plan

### 7.1 Button
Variants `primary | secondary | ghost | outline | danger | link`; sizes `sm | md | lg`; props `loading` (spinner + `aria-busy` + preserved width to prevent layout shift), `iconLeft`/`iconRight`, `fullWidth`, `asChild` for `next/link` composition. Single source for the focus ring and disabled treatment.
**Replaces:** ~20 hand-rolled buttons across auth, landing, exam, checklist, chat, onboarding.

### 7.2 Field / Input / Textarea / Select
`<Field label hint error required>` owns the id wiring: generates the id, sets `aria-describedby` to the hint and error nodes, sets `aria-invalid` on error, and renders the error with `role="alert"`. This closes the largest a11y gap in the codebase in one component.
**Replaces:** the input `className` string copy-pasted across `LoginForm`, `RegisterForm`, `ResetPasswordForm`, and all four onboarding steps.

### 7.3 Card
`Card` + `CardHeader`/`CardBody`/`CardFooter`, variants `flat | raised | interactive`, so the `shadow-2xs`-vs-`shadow-sm`-vs-`shadow-xl` inconsistency has one answer per role.

### 7.4 Badge, Alert, Modal, EmptyState, Skeleton, Spinner, Progress, Tabs, Tooltip, Icon
- **Badge:** `neutral | brand | success | warning | danger | info`, `sm | md` — unifies the pill chips currently written inline in profile, sidebar ("Soon"), pricing ("Most popular"), hero, speaking status.
- **Alert:** absorbs the three separate error-banner implementations in `profile/page.tsx`, `ChecklistView.tsx`, and `speaking/inline-alert.tsx`, which are visually different for identical purposes.
- **Modal:** proper focus trap, ESC, scroll lock, `aria-modal`, labelled title. `SubmitConfirmModal` becomes a consumer.
- **Icon:** a thin lucide wrapper pinning size (16/20/24) and stroke-width. Icon sizes are currently arbitrary (`size={16}`, `18`, `22`, `24`) with no rule, plus the sidebar defines ~7 bespoke inline SVGs that should move to lucide.

### 7.5 Enforcement
Add an ESLint rule (or a Vitest source-scan test in the style of the existing `test/unit/no-direct-service-urls.test.ts`) that fails on raw hex literals and on `bg-gray-*`/`bg-slate-*` in `app/` and `components/`, with `components/ui/` exempt. This is what stops the drift from re-accumulating, and there's already precedent for that test pattern in the repo.

---

## 8. Page-by-page redesign plan

| Surface | Current state | Plan |
|---|---|---|
| **Landing** | Works; template-grade below hero | Full redesign per §5 + §6 |
| **Navbar** | Dead mobile button, no mobile nav | Working slide-over, scroll states, tokens |
| **Footer** | Thin, 4 dead links | Expanded, links resolved or removed |
| **Login / Register / Forgot / Reset / Verify** | Decent card layout for the 3 that exist; duplicated inputs; unassociated errors; **Forgot Password and Verify Email routes don't exist**; `/reset-password` currently calls the wrong backend endpoint | Full rebuild — see §16 |
| **Onboarding** | 4-step wizard, gradient bg, `any` types, **`handleFinish` discards all data**, CV upload is simulated | Full rebuild — see §16 |
| **Chat** | Best-developed surface; framer-motion already in use; third color palette | Retint to tokens; message bubble hierarchy; consistent streaming/typing states; empty state with suggested prompts; mobile layout (currently `px-8` fixed, cramped < 640px); the header's three actions need a mobile overflow menu |
| **Exam hub (`/exam`)** | 437-line page, skill cards, resume banner, coming-soon panels | Extract to `Card`/`Badge`/`Alert`; proper progress visualisation; unify the "Soon" treatment with the sidebar's |
| **Exam shell** | Reading/Writing runtimes, 50/50 split, `w-44` nav rail | Focus-mode chrome; sticky timer with a warning threshold state; question nav rail as a real component with answered/flagged/current states; **the 50/50 split has no mobile story at all** — needs a tabbed passage/questions view |
| **Exam results** | 351 lines, chart.js | Score hero moment; band breakdown cards; per-section bars on tokens; share/retry actions |
| **Reading / Writing / Speaking** | Functional, three palettes | Retint; unify submit/confirm flows on `Modal`; speaking waveform + mic button already good — align colors only |
| **Checklist** | `/checklist/[programId]` only, no index | Restyle phases as a vertical timeline with progress; item rows on `Checkbox`; preserve the print rules exactly; add an index/empty state |
| **Profile** | Read-only `dl` grid | Section cards, avatar, completeness meter, edit affordances (UI only) |
| **Opportunities / Dashboard** | **Do not exist** (`href: null` in sidebar) | Out of scope to build. Deliver designed empty/coming-soon states and a route shell so the sidebar stops linking to nothing |
| **App shell** | `sidebar.tsx` 397 lines mixing nav, mobile drawer, identity, and inline SVGs | Split into `AppShell` / `Sidebar` / `SidebarNav` / `UserMenu`; icons → lucide; `aria-current` on the active item; collapsible on desktop |
| **Empty / Loading / Error** | No `loading.tsx`, no `not-found.tsx`; 3 divergent error banners | `EmptyState` primitive; route-level `loading.tsx` with skeletons matching real layout; a global `not-found.tsx`; all error banners → `Alert` |

---

## 9. Animation strategy

**Budget:** motion is for orientation and feedback, never decoration. If a user can't name what an animation told them, it's cut.

**Tiers:**
1. **Micro (100–150ms)** — hover, focus, press. CSS only, `transition-colors`/`transition-shadow` with explicit tokens. Never `transition` (all-properties) again, which is the current default and animates layout.
2. **State (200–320ms)** — enter/exit of alerts, modals, dropdowns, toasts. framer-motion where exit animation is needed; CSS otherwise.
3. **Scroll reveal (320–500ms)** — marketing only. A single shared `<Reveal>` client component using `whileInView` with `once: true`, staggering children by 60ms. Applied to Features, How It Works, Proof, Pricing, CTA.
4. **Signature (bespoke)** — three moments only: hero chat mock assembling, hero stat count-up, exam results band-score reveal.

**Shared config:** `lib/motion.ts` exports the duration/easing constants and named variants (`fadeUp`, `fadeIn`, `scaleIn`, `staggerChildren`) so nothing declares `duration: 0.4` inline again.

**Reduced motion:** the global CSS kill switch (§4) plus framer-motion's `useReducedMotion` in every animated component — opacity-only fallbacks, no transforms. Non-negotiable; currently absent entirely.

**Server-component discipline:** `<Reveal>` is a thin client wrapper that takes `children` — the wrapped content stays server-rendered. This is how the landing page keeps its near-zero client bundle.

---

## 10. Responsive strategy

**Mobile-first, four breakpoints:** base (<640) / `sm` 640 / `md` 768 / `lg` 1024 / `xl` 1280. Content max-width standardised at `max-w-7xl` for marketing, `max-w-3xl` for reading-heavy app pages.

**Known breakages to fix:**
- **Landing has no mobile navigation** — the hamburger is inert (§0.6).
- **Chat uses fixed `px-8`** on the shell and its input row; below 400px this leaves very little content width.
- **Exam shell's `w-1/2` + `w-1/2` split has no mobile treatment** — on a phone this is two unusable 180px columns. Needs a tab switch between passage and questions.
- **Reading nav rail is a fixed `w-44`** with no collapse.
- **Profile uses `grid-cols-2`** unconditionally — cramped on small screens.
- **Landing sections all use `py-24`** flat; should scale `py-16 / md:py-20 / lg:py-28`.

**Touch targets:** minimum 44×44px for all interactive elements — several current chips and icon buttons are `py-1.5` (~28px tall).

**Container queries:** Tailwind v4 supports them natively; use for cards that appear in both wide and narrow slots (opportunity cards, checklist rows) rather than proliferating breakpoint variants.

---

## 11. Accessibility improvements

Target: WCAG 2.1 AA, and hold the existing Lighthouse ≥ 90 gate on the landing page while extending that spec to `/login`, `/chat`, and `/exam`.

1. **Forms** — `Field` wires `aria-describedby`, `aria-invalid`, and `role="alert"` errors everywhere (currently zero `aria-describedby` in the codebase).
2. **Focus** — one `:focus-visible` ring token applied globally in the base layer; audit every `outline-none`; the ring must be visible on both light and brand-colored surfaces.
3. **Landmarks & headings** — one `<h1>` per page (exam and chat pages currently start at `h1` in a banner then jump); proper `<main>`/`<nav>`/`<aside>`; a skip-to-content link in the root layout.
4. **Keyboard** — mobile nav and modals get focus traps and ESC; the exam question nav must be arrow-key navigable; no keyboard traps in the chat composer.
5. **Live regions** — chat streaming, exam timer warnings, save confirmations, and toast alerts announce via `aria-live` (only 2 uses today).
6. **Contrast** — every semantic token pair validated at authoring time; the current `text-gray-400` on white (~2.8:1) used for metadata across profile, reading, and chat **fails AA** and must move to a `fg-subtle` token that passes.
7. **Icons** — decorative icons get `aria-hidden`; icon-only buttons get `aria-label` (the sidebar and chat toolbar have several without).
8. **Images** — only 1 `alt` attribute exists in the entire codebase; audit as visuals are added.
9. **Motion** — `prefers-reduced-motion` honoured globally.
10. **`aria-current="page"`** on active nav in both sidebar and navbar.

---

## 12. Visual hierarchy improvements

- **Fix the type floor.** `text-sm`/`text-xs` account for 294 of ~370 sizing declarations. Body copy moves to `text-base` (16px); `text-xs` is reserved for metadata and badges only. This single change does more for perceived quality than any other item in this plan.
- **Establish display type.** Serif at `4xl`+ for page and section headings, sans for everything else — giving the product an editorial voice instead of a dashboard voice.
- **Vertical rhythm.** Section padding, heading→body gaps, and card internal padding get fixed values per role instead of the current per-file improvisation.
- **Reduce border noise.** Today nearly every group is boxed in `border-slate-200`. Move to background-tint grouping (`bg-bg-subtle`) and whitespace; reserve borders for genuinely interactive or enclosing surfaces.
- **One accent per view.** Amber accent is used for the single most important action or datum on a screen; brand green carries everything else.
- **Data emphasis.** Scores, match percentages, and band results are the emotional payload of this product and are currently rendered at the same weight as labels. They get dedicated display-scale treatment.

---

## 13. Performance considerations

- **Preserve zero-JS landing.** `Reveal` and the scroll-aware navbar are the only client components on `/`; everything else stays server-rendered. Measure with a bundle check before/after.
- **framer-motion is ~34 kB gz.** It's already a dependency and already loaded on `/chat`. Keep it *off* the landing critical path — the landing reveal animations use CSS `@keyframes` + `IntersectionObserver` in a ~1 kB component rather than pulling framer-motion into the marketing bundle. framer-motion stays scoped to the app surfaces where it already lives.
- **Fonts.** Geist is loaded via `next/font` (self-hosted, no layout shift) — restoring it costs nothing since it's already downloaded and merely overridden. Adding a serif display family means one more family: subset to latin, `display: swap`, and load only the weights used (likely 400/600).
- **Images.** No `next/image` usage today. Any screenshots added to How It Works must go through it with explicit dimensions to protect CLS.
- **Icons.** lucide-react is tree-shakeable per-icon; the audit should confirm no barrel imports creep in.
- **CSS.** Tailwind v4 tokens add negligible CSS; the token file is a few kB uncompressed.
- **Targets:** Lighthouse Performance ≥ 90 and Accessibility ≥ 95 on `/`, CLS < 0.1, LCP < 2.5s. The existing `test/seo/lighthouse.spec.ts` is extended to assert these rather than accessibility alone.

---

## 14. Incremental implementation phases

Each phase is independently shippable and leaves the app in a working state. Nothing is a big-bang rewrite.

**Phase 0 — Foundation (no visual change intended)**
Token system in `globals.css`; delete the Arial override and the duplicate `:root`; delete the broken dark-mode block and author the dark token layer; add `cn.ts`, `motion.ts`, `clsx`, `tailwind-merge`. *Exit: app renders in Geist, nothing else visibly moves.*

**Phase 1 — Primitives**
Build `components/ui/*` with the full variant set. Not yet adopted anywhere. Add the lint/scan rule but scoped as a warning. *Exit: primitives exist and are unit-tested.*

**Phase 2 — Landing page**
Full redesign per §5, new CTA per §6, Trust/Proof/FAQ sections, working mobile nav. Update the e2e specs that assert landing copy. *Exit: `/` is production-grade; Lighthouse gates pass.*

**Phase 3 — Auth + Onboarding** (re-scoped, now first after Phase 2 — see §16 for the full detailed plan)
Rebuild Register, Login, Forgot Password, Reset Password, Verify Email, and the Onboarding wizard on `Field`/`Button`/`Alert`/`Progress`. Closes the biggest form-a11y gap, closes two missing routes, and fixes the onboarding data-loss bug. *Exit: no hand-rolled inputs remain in `components/auth/` or `components/onboarding/`; every route in the journey exists and persists correctly against the real backend.*

**Phase 4 — App shell**
Split `sidebar.tsx`, build `AppShell`/`PageHeader`, unify the app canvas onto tokens, add `aria-current`, replace inline SVGs with lucide. This is the phase that kills the marketing/app visual split. *Exit: one neutral ramp and one green across all authenticated routes.*

**Phase 5 — States**
`EmptyState`, route `loading.tsx` files with layout-matched skeletons, global `not-found.tsx`, consolidate the three error banners onto `Alert`. *Exit: every route has a designed loading, empty, and error state.*

**Phase 6 — Chat**
Retint, message hierarchy, empty state with suggested prompts, mobile layout, header overflow menu.

**Phase 7 — Exam surfaces**
Exam hub, shell chrome, results moment, reading/writing/speaking retint, mobile passage/questions tabs.

**Phase 8 — Checklist, Profile, and shells for Opportunities/Dashboard**
Timeline checklist, profile cards + completeness, designed coming-soon routes.

**Phase 9 — Polish sweep**
Motion pass with reduced-motion verification, full contrast audit, keyboard walkthrough of every flow, responsive pass at 320/375/768/1024/1440, Lighthouse across all four gated routes, flip the lint rule from warning to error.

---

## 15. Implementation order by impact

Ranked by *user-visible quality gained per unit of work*, which is the order I'd actually build in:

| # | Work | Effort | Impact | Why here |
|---|---|---|---|---|
| 1 | Phase 0 tokens + **font fix** | S | **Very high** | The whole app is currently in Arial. One line, enormous perceived-quality delta. Unblocks everything. |
| 2 | Type-scale correction (`text-sm` → `text-base` body) | S | **Very high** | Cheapest single change that stops the "student project" read. |
| 3 | Phase 1 primitives | M | High | Force multiplier — every later phase gets faster and more consistent. |
| 4 | Phase 2 landing + CTA | L | **Very high** | The explicit priority, and the highest-traffic surface. |
| 5 | Phase 4 app shell unification | M | High | Ends the three-palette problem; every authenticated page benefits at once. |
| 6 | Phase 3 auth + onboarding | M | High | First authenticated impression; also the biggest a11y win. |
| 7 | Phase 5 states | M | High | Empty/loading/error states are the clearest senior-vs-junior tell. |
| 8 | Phase 7 exam surfaces | L | Medium-high | Core product value, but behind auth and lower traffic. |
| 9 | Phase 6 chat | M | Medium | Already the most polished surface; mostly retinting + mobile. |
| 10 | Phase 8 checklist/profile/shells | M | Medium | Lower traffic. |
| 11 | Phase 9 polish sweep | M | Medium | Necessary to hold quality, but only meaningful once 1–10 exist. |

**Fast path:** items 1–4 alone (Phase 0 + type + primitives + landing) capture the majority of the visible transformation.

---

## 16. Phase 3 — Auth + Onboarding (detailed plan)

Re-prioritized ahead of the app shell at the user's request: this is the one continuous journey a brand-new user completes before ever seeing the product, so it now ships immediately after the landing page, at the same quality bar. **No backend business logic changes** — this phase wires the frontend to endpoints and DTOs that already exist server-side, and fixes one place where the frontend currently calls the *wrong* one.

### 16.1 What the backend already supports (confirmed by reading `services/gateway` + `services/user`)

| Step | Endpoint | Status |
|---|---|---|
| Register | `POST /users` | Frontend already calls this correctly. |
| Login | `POST /auth/login` | Frontend already calls this correctly. |
| Request password reset email | `POST /auth/forgot-password` (`gateway/server.go:138`) | **Exists, but nothing in the frontend calls it.** `ResetPasswordForm.tsx` currently calls `POST /auth/reset-password` instead — the wrong endpoint — for the "send me a link" step. This is a bug to fix, not a redesign choice. |
| Confirm reset with token | `POST /auth/reset-password` with `{ token, newPassword }` (`gateway/server.go:139`, DTO at `services/user/src/users/dto/reset-password.dto.ts`) | **Exists end-to-end.** No frontend page consumes it — there is nowhere today a user can actually set a new password. |
| Verify email | `GET /auth/verify-email/:token` (`gateway/server.go:140`) | **Exists end-to-end**, and registration already triggers the email (`users.service.ts` publishes `EmailVerificationRequired`). No frontend page exists to land the link on. |
| Onboarding — academic/language/target fields | `PUT /users/:id/profile` (`services/user/src/profile/profiles.controller.ts:9`) | DTO and service logic exist. **Not proxied through the gateway** — `server.go` only proxies `GET /api/profile`, no `PUT`. See §16.5 below; this is the one item that needs a decision from you. |
| Onboarding — CV upload | `POST /api/writing/cv/upload` (`gateway/server.go:177`) | Exists and is real (used by the writing/CV-review feature). Reusable as-is for the onboarding CV step. |

Net effect: **Register, Login, Forgot Password, Reset Password, and Verify Email can all be built end-to-end this phase with zero backend changes.** Onboarding's CV step can too. Onboarding's profile fields (academic/language/target) need one missing gateway proxy route added — a routing addition, not new business logic — flagged as a decision in §16.5 rather than assumed.

### 16.2 Route map

```
/register                    existing, rebuilt
/login                       existing, rebuilt
/forgot-password             NEW — "send me a reset link" (email only)
/reset-password?token=...    rebuilt — becomes the CONFIRM step (new password + confirm),
                              reading the token from the URL query
/verify-email/[token]        NEW — lands the email link, calls the verify endpoint on mount,
                              shows a designed success/expired/error state
/onboarding                  existing, rebuilt, 4 steps + real persistence
```

`/reset-password` changes meaning (request → confirm) because that's what the backend endpoint at that name actually does; the "request" step moves to the new `/forgot-password` route, matching the backend's own naming. The Login page's "Forgot password?" link is repointed from `/reset-password` to `/forgot-password`.

### 16.3 Shared auth shell (new)

Currently Register/Login/Reset each independently copy-paste the same gradient background + logo + card. Replacing with one shared layout:

- `app/(auth)/layout.tsx` — route group, so the URL doesn't change. Split screen on `lg+`: a brand panel (deep forest, the same visual language as the landing CTA/footer — soft radial glow, wordmark, a short rotating line of reassurance copy) on one side, the form card on the other. Below `lg`, the brand panel collapses to a compact top band so the form is reached without scrolling.
- One wordmark-linked-home header, one card container, one `max-w` — defined once, not six times.
- Forms stay Client Components (they need state); the layout and card chrome stay Server Components.

### 16.4 Per-page plan

**Register / Login** — rebuilt on `Field` (wires `aria-describedby`/`aria-invalid`/`role="alert"` automatically — closes the exact gap `field.tsx` was already built for), `Button` (`loading` state via `aria-busy`, no more disabled-looks-broken), `Alert` for top-level failures (e.g. "email already registered"). Add: password visibility toggle, inline password-strength hint on Register (backend still enforces its own rule; this is UX guidance only, not new validation logic), surfacing the actual backend error message on Login instead of a hardcoded generic string, and a designed success moment on Register before the redirect to `/login` — currently silent.

**Forgot Password (new)** — single email field, submits to `POST /auth/forgot-password`. Success state doesn't reveal whether the address exists (existing backend behavior, preserved) — copy reads "If that email exists, we've sent a reset link," with a resend affordance after a short cooldown.

**Reset Password (confirm)** — reads `token` from the URL. States: token missing/malformed (shown immediately, no submit), the new-password + confirm form, an inline password-match check, loading, success (redirect to `/login` with a "password updated" toast-style banner), and an expired/invalid-token error state distinguishing "this link expired, request a new one" from a generic failure.

**Verify Email (new)** — the link's landing page. On mount, calls `GET /auth/verify-email/:token` and shows one of: verifying (spinner), success ("email verified" + continue-to-app action), already-verified, or expired/invalid (with a resend-verification affordance if the backend supports it — otherwise a "contact support" fallback, checked against the actual `auth.controller.ts` surface before promising resend).

### 16.5 Onboarding wizard rebuild

- **Step indicator** — replace the manual percentage-width bar with the `Progress` primitive plus a real stepper (completed/current/upcoming, step labels visible on `sm+`, collapsing to just "Step 2 of 4" + bar on mobile).
- **State** — lift the 4 steps' data into one wizard state in `app/onboarding/page.tsx` (already mostly the shape today), but sync the current step index to a URL query param (`?step=2`) so back/forward and refresh don't silently lose position the way they can today.
- **Validation** — keep each step's existing field-level validation logic (it's already fairly thorough), but move error rendering onto `Field`'s `aria-describedby`/`role="alert"` wiring instead of the current plain colored `<span>`s.
- **CV upload step** — replace the entirely simulated `simulateUploadAndProcessing()` with a real upload to `POST /api/writing/cv/upload`, real progress from the upload request, and replace the `alert()` on invalid file type with an inline error state on the dropzone. Add real size/type limits surfaced before upload starts, not after. Drag-and-drop, file preview chip, and a remove/replace affordance once a file is attached.
- **Persistence (the actual bug fix)** — `handleFinish` currently does nothing but redirect ([onboarding/page.tsx:31](../services/frontend/app/onboarding/page.tsx#L31)). It will call `PUT /users/:id/profile` with the accumulated academic/language/target data before redirecting to `/chat`, with a loading state on the final step's submit button and an `Alert` on failure that keeps the user's data on-screen (never silently discard a completed wizard on a network error).
- **Decision needed from you (§16.5 is the one blocker):** `PUT /users/:id/profile` is implemented in the user service but not exposed through the gateway (`server.go` proxies `GET /api/profile` only). Wiring onboarding's persistence therefore needs one proxy route added in `services/gateway/server.go` — a routing addition using the existing handler pattern, not new business logic. I'd treat this as in-scope (it's the line that turns onboarding from cosmetic to functional), but it does touch a file outside `services/frontend`, so I'm flagging it rather than just doing it. See open question 7 below.

### 16.6 Empty / loading / error / success states (per the explicit ask)

Every one of the 6 flows gets, at minimum: an idle state, a submitting state (`Button loading`, form disabled, no layout shift), a field-error state (`Field` + `role="alert"`), a request-level error state (`Alert`, specific message where the backend gives one), and a success state that is never just a silent redirect — Register, Reset-confirm, and Onboarding-finish all show a brief confirmation before navigating on.

---

## Open questions

1. **Brand green:** confirm consolidating on deep forest `#0d4d3a` over `emerald-700` (§1). This is the one decision that affects every subsequent file.
2. **Serif display type:** the app shell already uses `font-serif` for headings. Keep and formalise it, or go all-sans? I recommend keeping it — it's what gives GOA a voice.
3. **Real content for Trust and Proof sections:** are there real partner institutions or user testimonials? If not, those sections ship as outcome metrics rather than fabricated logos/quotes.
4. **Landing stats:** "95% Match Accuracy" — is this measured? If not it should be replaced rather than restyled.
5. ~~**Onboarding persistence:** `handleFinish` discards the wizard's data.~~ Resolved by re-scoping: Phase 3 now fixes this directly. See §16.5.
6. **e2e copy coupling:** 23 `getByText` assertions will break on rewording. Confirm I should update the specs alongside each phase.
7. **Gateway proxy route for onboarding persistence (new, blocking §16.5):** `PUT /users/:id/profile` exists in the user service but isn't exposed through the gateway. May I add the one proxy route in `services/gateway/server.go` (following the existing pattern for the other `/users/:id/...` routes) so onboarding can actually save? This is the only place Phase 3 touches anything outside `services/frontend`. If you'd rather I not touch the gateway at all, the alternative is shipping the onboarding UI fully rebuilt but with persistence still stubbed, and I'd flag that clearly on screen rather than silently redirect as today.
8. **Reset-password email enumeration:** confirmed the backend already returns a generic "if it exists" response for `/auth/forgot-password` — the frontend will match that copy rather than confirming/denying account existence.

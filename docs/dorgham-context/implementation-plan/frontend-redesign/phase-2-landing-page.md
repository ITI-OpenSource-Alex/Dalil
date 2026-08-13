# Phase 2 — Landing Page Redesign

**Status:** ✅ Complete
**Note on provenance:** reconstructed from current repository state and the origin plan (§5, §6, §14) — see the provenance note in [phase-0-foundation.md](phase-0-foundation.md).

## Goal

Turn the landing page from a feature list that stops after the pricing table into an actual conversion page, on the Phase 1 design system, while preserving its one genuine pre-existing asset: it shipped as fully server-rendered with zero client JS.

## Scope

`app/page.tsx` and everything under the new `components/marketing/` directory (renamed from `components/landing/`, which is deleted). Out of scope: any authenticated-app page, any auth page (those are Phase 3/4).

## Architecture decisions

**`components/landing/` retired in favor of `components/marketing/`.** The rename reflects that these components serve the pre-authentication surface generally (navbar, footer, wordmark) and matches the origin plan's directory layout in §2.

**Section order redesigned around a narrative arc**, not just a visual refresh — the original page was Navbar → Hero → Features → HowItWorks → Pricing → Footer, which has a hook, an explanation of what the product does, an explanation of how, and a cost — then just stops. The new order is:

```
Navbar → Hero → TrustBar → Features → HowItWorks → Proof → Pricing → FAQ → CTA → Footer
```

read as *hook → credibility → what → how → evidence → cost → objections → ask*. `Proof` and `CTA` are the two dark-surface anchors; everything between alternates canvas/subtle, so the page's visual rhythm is a property of the whole page rather than nine independently-styled bands (see the ordering rationale documented directly in `app/page.tsx`'s file comment).

**Client-JS is scoped to three leaf components**: `Navbar` (mobile menu + scroll state), `Reveal` (scroll-triggered fade/rise, used by every section below the hero), and a stat counter inside `HeroStats`. Every section itself (`Hero`, `TrustBar`, `Features`, `HowItWorks`, `Proof`, `Pricing`, `FAQ`, `Footer`) remains a Server Component; `Reveal` wraps their content rather than the sections becoming client components themselves — this is the mechanism that keeps the "server-first" principle real rather than aspirational.

**`<noscript>` fallback for scroll reveals.** Reveal-hidden sections ship their hidden state directly in the HTML (`data-reveal` + `opacity-0`/transform via CSS), so a `<noscript>` block in `app/page.tsx` restores full visibility if JS never runs, rather than leaving the page blank for that user.

## UI/UX decisions

- **Navbar**: rebuilt with a working mobile menu (the pre-existing hamburger button had no `onClick`, no `aria-label`, no `aria-expanded` — a dead control) — slide-over panel, focus trap, Escape-to-close with focus returned to the trigger, body-scroll lock while open. Height reduced from a disproportionate 80px to 64px. Scroll-state (transparent over the hero, solid + bordered once scrolled) implemented as a small client leaf.
- **Hero**: kept structurally per the original request; changes are polish — the three-color `emerald-50 → white → orange-50` gradient (flagged in the audit as reading as "template") replaced with a subtler layered background; headline moved to the serif display face at responsive `text-5xl`/`lg:text-7xl`; the hero chat mock elevated with a real shadow and browser-chrome framing, with its opportunity rows animating in on scroll rather than sitting inert; unsubstantiated stat claims addressed per Open Question 4 in the origin plan.
- **New sections**: `TrustBar` (quiet credibility row directly under the hero), `Proof` (outcome/testimonial band, the page's dark midpoint anchor), `FAQ` (native `<details>`/`<summary>`, so it stays server-rendered with zero JS, covering the real objections: pricing, IELTS scoring accuracy, data handling, supported countries, how matching works), `CTA` (the closing ask, full-bleed dark forest band per §6 of the origin plan).
- **Fixed conversion-path conflict**: every primary CTA across the page now points to one consistent destination rather than Navbar/Hero routing to `/onboarding` while Pricing routed to `/register` — resolved by the same decision that shaped Phase 3's route map (register-first, onboarding second, since onboarding didn't persist data until Phase 3 fixed it).
- **Footer**: expanded from a thin single-row footer to a fuller structure; dead `href="#"` links resolved or removed.

## Components introduced

None new in `components/ui/` — this phase is entirely adoption of Phase 1's primitives plus marketing-specific composition components: `Navbar`, `Hero`, `TrustBar`, `Features`, `HowItWorks`, `Proof`, `Pricing`, `FAQ`, `CTA`, `Footer`, `Reveal`, `Section` (shared section-wrapper), `Wordmark` (the brand lockup — a forest roundel with a serif "G" plus the "goa" wordmark — later reused as-is by Phase 4's sidebar, so the brand identity doesn't change on login), `HeroDemo`, `Enter` (marketing-scoped animation helper).

## Files created

- `services/frontend/components/marketing/navbar.tsx`
- `services/frontend/components/marketing/hero.tsx`
- `services/frontend/components/marketing/hero-demo.tsx`
- `services/frontend/components/marketing/trust-bar.tsx`
- `services/frontend/components/marketing/features.tsx`
- `services/frontend/components/marketing/how-it-works.tsx`
- `services/frontend/components/marketing/proof.tsx`
- `services/frontend/components/marketing/pricing.tsx`
- `services/frontend/components/marketing/faq.tsx`
- `services/frontend/components/marketing/cta.tsx`
- `services/frontend/components/marketing/footer.tsx`
- `services/frontend/components/marketing/reveal.tsx`
- `services/frontend/components/marketing/section.tsx`
- `services/frontend/components/marketing/wordmark.tsx`
- `services/frontend/components/marketing/enter.tsx`

## Files modified

- `services/frontend/app/page.tsx` (full rewrite onto the new section order and components)
- `services/frontend/test/e2e/*` — landing-page e2e specs updated for the new section structure and copy (the origin plan's §0.9 flagged 23 `getByText` assertions as coupled to exact copy; any wording change had to land with the matching spec update in the same commit)

## Files deleted

- `services/frontend/components/landing/Features.tsx`
- `services/frontend/components/landing/Footer.tsx`
- `services/frontend/components/landing/Hero/Hero.tsx`
- `services/frontend/components/landing/Hero/HeroButtons.tsx`
- `services/frontend/components/landing/Hero/HeroChat.tsx`
- `services/frontend/components/landing/Hero/HeroContent.tsx`
- `services/frontend/components/landing/Hero/HeroStats.tsx`
- `services/frontend/components/landing/Hero/opportunities.ts`
- `services/frontend/components/landing/HowItWorks.tsx`
- `services/frontend/components/landing/Navbar.tsx`
- `services/frontend/components/landing/Pricing.tsx`

## Accessibility improvements

- Working mobile navigation where none existed (the audit's §0.6 called this out specifically: "There is no mobile navigation on the landing page at all").
- `aria-expanded`, focus trap, and Escape-to-close added to the mobile menu.
- FAQ built on native `<details>`/`<summary>` — accessible disclosure semantics for free, no custom ARIA required.
- `test/seo/lighthouse.spec.ts` gates the landing page's Lighthouse accessibility score at ≥ 90; this phase is what the gate was already holding the page to, and is extended in the origin plan's intent to cover performance ≥ 90, CLS < 0.1, LCP < 2.5s (verification status of those specific thresholds should be re-confirmed as part of Phase 6's polish sweep, which is where the plan schedules the full Lighthouse audit across all gated routes).

## Performance improvements

- Landing page confirmed to still ship with only `Navbar`, `Reveal`, and the hero stat counter as client JS — everything else server-rendered, preserving the pre-redesign zero-JS property while looking completely different.
- framer-motion (already a dependency, ~34kB gzipped, already loaded on `/chat`) deliberately kept off the landing critical path — scroll reveals use CSS `@keyframes` + `IntersectionObserver` in `Reveal` rather than pulling framer-motion into the marketing bundle.

## Verification performed

- `npm run build` / `tsc --noEmit` clean.
- Landing-page e2e specs updated and passing against the new markup/copy.
- Lighthouse accessibility gate (`test/seo/lighthouse.spec.ts`) held at ≥ 90.

## Screenshots

Not captured as part of this documentation pass (this phase predates the conversation these docs were authored from). The live page is inspectable at `/` in a running dev/build server; Phase 3 and Phase 4's screenshot sets (referenced in their own docs) show the same design language in use on the auth and app-shell surfaces this phase established the visual vocabulary for.

## Lessons learned

- Reordering sections around an explicit narrative arc (documented directly in the page's own file comment) rather than only restyling in place is what turned "a list of features" into "an argument" — a structural change, not a cosmetic one, and worth calling out because it's the kind of decision that's easy to skip when a redesign task is framed as "make it look nicer."
- Keeping `Reveal` as a thin wrapper around server-rendered children (rather than promoting whole sections to client components) is the concrete technique, not just the stated principle, that kept the zero-JS landing page real through a complete visual overhaul — worth carrying into Phase 5/6 wherever a similar scroll-reveal or animation need appears on any other server-rendered surface.

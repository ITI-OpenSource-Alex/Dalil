# Phase 1 — Design System Primitives

**Status:** ✅ Complete
**Note on provenance:** reconstructed from current repository state and the origin plan (§7, §14) — see the provenance note in [phase-0-foundation.md](phase-0-foundation.md).

## Goal

Build the component library that didn't exist before this effort — `components/ui/` contained exactly three files (`skeleton.tsx`, `checkbox.tsx`, `sidebar.tsx`) and no Button, Input, Card, Badge, Modal, Alert, Field, Select, Textarea, Tabs, or Tooltip. Every later phase depends on this one: it's the force multiplier that makes every subsequent redesign faster and enforces consistency by construction rather than by review discipline.

## Scope

All of `components/ui/*` — 20 primitive files by the end of this phase (see full list below). Primitives are built and unit-tested in this phase but not yet universally adopted by every page; adoption happens phase by phase as each surface is redesigned (Phase 2 for marketing, Phase 3 for auth/onboarding, Phase 4 for the app shell, Phases 5–6 for the remainder).

## Architecture decisions

**Primitives own no product knowledge.** Every file in `components/ui/` takes props and renders — none of them import from `lib/*-api.ts`, none fetch data, none know what a "checklist" or an "exam session" is. Domain components (in `components/chat/`, `components/exam/`, etc.) compose these primitives; they never write raw Tailwind color utilities themselves.

**Server/client boundary is a first-class architectural constraint, not an afterthought.** A primitive that gains a `"use client"` directive drags every page importing it across the server/client boundary — for the marketing pages, which are entirely server-rendered and are the highest-traffic surface, that turns a static page into a hydrated one, invisibly. The codebase enforces this with [`test/unit/ui-server-boundary.test.ts`](../../../../services/frontend/test/unit/ui-server-boundary.test.ts): two explicit lists (`MUST_BE_SERVER_RENDERABLE`, `CLIENT_BY_DESIGN`) that every file in `components/ui/` must appear in exactly once, plus a check that no server-renderable primitive imports a client-only one. Moving a component between these lists is a deliberate decision; the test is what stops it happening by accident.

**No CVA dependency.** Variants (`Button`'s `variant`/`size`, `Badge`'s `tone`/`variant`, `Card`'s `variant`) are implemented as plain typed lookup objects (`Record<Variant, string>`) rather than adding `class-variance-authority`. This buys the same ergonomics without another dependency.

**Class composition goes through `cn()` exclusively.** Every primitive accepts a `className` prop and merges it last via `lib/cn.ts`'s `cn()`, so a caller's override always wins instead of depending on Tailwind's stylesheet-emission order — the actual bug the pre-redesign codebase had, since it concatenated class strings with template literals with no merge logic at all.

**Token-discipline is machine-enforced, not a style-guide entry.** The same `ui-server-boundary.test.ts` file also runs a "design token discipline" suite over every file in `components/ui/`: no raw hex literals (`#[0-9a-fA-F]{3,8}`), no default Tailwind neutral ramps (`gray-*`/`slate-*`/`zinc-*`/`neutral-*`/`stone-*`). This is what the origin plan's §7.5 "enforcement" item became in practice — implemented as a Vitest source-scan test (following the precedent of the pre-existing `test/unit/no-direct-service-urls.test.ts`) rather than a separate ESLint rule, so it runs in the same `vitest run` every other test does.

## UI/UX decisions

**`Field` is the single biggest accessibility fix in the whole redesign**, and it shipped in this phase specifically so every later form-building phase gets it for free. It wires `aria-describedby` (pointing at hint and error nodes), `aria-invalid` on the control when there's an error, and renders the error text with `role="alert"` — automatically, from the presence of an `error` prop. Before this, `aria-describedby` had zero uses anywhere in the codebase.

**`Icon` pins size and stroke-width** to a four-step scale (`xs`/`sm`/`md`/`lg` → 14/16/20/24px), replacing arbitrary inline `size={16}`, `{18}`, `{22}`, `{24}` calls with no rule, and defaults to `aria-hidden` unless a `label` prop is explicitly given — so icon-only buttons are the one place an accessible name is required, and every other icon is correctly hidden from assistive tech rather than double-announced next to its own visible label.

**`Button`'s `loading` state uses the native `disabled` attribute** (to prevent double-submission with zero client JS required by the component itself) but restores full opacity via `aria-busy:opacity-100`, because a *busy* button reading as a *disabled/unavailable* one is a distinct, worse failure mode. The label stays in the DOM at `invisible` rather than being replaced, so the button never resizes between idle and loading — a resizing submit button mid-request was flagged in the original audit as a layout-shift defect.

**`Alert` absorbed three separate hand-rolled error-banner implementations** (previously visually different across `profile/page.tsx`, `ChecklistView.tsx`, and speaking's inline alert, for identical purposes) into one component with tone-based defaults for announcement politeness: `danger` announces as `role="alert"` (assertive — it reports a failure the user must act on), every other tone as `role="status"` (polite), and an explicit `announce="none"` escape hatch for alerts that are part of a page's static initial content and shouldn't be announced as if they'd just appeared.

## Components introduced

Server-renderable (no `"use client"`, zero client JS cost to import): `Button`, `Card`/`CardHeader`/`CardTitle`/`CardDescription`/`CardBody`/`CardFooter`, `Badge`, `Alert`, `Heading`, `Text`/`Eyebrow`, `Icon`, `Spinner`, `Skeleton`/`SkeletonGroup`, `Progress`, `EmptyState`, `PageContainer` (added in Phase 4, folded into this same list — see [phase-4-app-shell.md](phase-4-app-shell.md)).

Client-only (hooks or Radix, by design): `Field`/`useFieldControl`, `Input`/`Textarea`/`Select`, `Checkbox`, `Radio`/`RadioGroup`, `Switch`, `Modal`/`ModalContent`/`ModalTrigger`/`ModalClose` (built on `@radix-ui/react-dialog` rather than hand-rolled, specifically because a correct dialog has to trap focus, restore it to the trigger on close, mark the rest of the page `aria-hidden`, lock body scroll without layout shift, and close on Escape — every one of which is a place hand-written dialogs go subtly wrong), `Tabs`/`TabsList`/`TabsTrigger`/`TabsPanel` (Radix), `Tooltip`/`TooltipProvider` (Radix).

All exported from one barrel, `components/ui/index.ts`, so the design system's surface stays visible in one place rather than requiring callers to reach into individual files.

## Files created

- `services/frontend/components/ui/button.tsx`
- `services/frontend/components/ui/card.tsx`
- `services/frontend/components/ui/badge.tsx`
- `services/frontend/components/ui/alert.tsx`
- `services/frontend/components/ui/heading.tsx`
- `services/frontend/components/ui/text.tsx`
- `services/frontend/components/ui/icon.tsx`
- `services/frontend/components/ui/spinner.tsx`
- `services/frontend/components/ui/progress.tsx`
- `services/frontend/components/ui/empty-state.tsx`
- `services/frontend/components/ui/field.tsx`
- `services/frontend/components/ui/input.tsx` (also exports `Textarea`, `Select`, `CONTROL_BASE`/`CONTROL_VALID`/`CONTROL_INVALID`)
- `services/frontend/components/ui/radio.tsx`
- `services/frontend/components/ui/switch.tsx`
- `services/frontend/components/ui/modal.tsx`
- `services/frontend/components/ui/tabs.tsx`
- `services/frontend/components/ui/tooltip.tsx`
- `services/frontend/components/ui/index.ts` (barrel)
- `services/frontend/test/unit/ui-primitives.test.tsx`
- `services/frontend/test/unit/ui-server-boundary.test.ts`

## Files modified

- `services/frontend/components/ui/checkbox.tsx` (pre-existing file, rewritten onto tokens and folded into the same variant/accessibility conventions as the new primitives)
- `services/frontend/components/ui/skeleton.tsx` (pre-existing file, rewritten onto tokens)
- `services/frontend/package.json` (`@radix-ui/react-dialog`, `@radix-ui/react-tabs`, `@radix-ui/react-tooltip` added)

## Accessibility improvements

- `Field` closes the `aria-describedby`/`aria-invalid`/`role="alert"` gap identified as the single largest a11y defect in the original audit (§0.6: zero `aria-describedby` uses codebase-wide before this phase).
- `Icon`'s default-`aria-hidden` behavior and required-`aria-label`-when-icon-only convention (enforced at the `ButtonProps`/`IconOnlyProps` type level for `Button`) close the "icon-only buttons with no accessible name" gap called out in the audit.
- `Modal` provides a correct focus trap, `aria-modal`, and Escape/overlay dismissal via Radix, replacing what would otherwise be a hand-rolled dialog with none of those guarantees.
- `Progress` exposes `role="progressbar"` with `aria-valuenow`/`aria-valuemax`/`aria-valuetext`, rather than a purely visual bar.

## Performance improvements

- Server-renderable primitives (11 of the 20) ship zero client JS on their own — a marketing page built entirely from `Button`, `Card`, `Badge`, `Alert`, `Heading`, `Text`, `Icon`, `Spinner`, `Skeleton`, `Progress`, `EmptyState` stays fully static. This is the mechanism, not just the goal, behind the landing page's near-zero client bundle (verified in Phase 2).
- `Button`'s `asChild` prop is implemented with `React.cloneElement` rather than `@radix-ui/react-slot`, specifically because Slot is a client component and would have pulled `Button` — and every marketing page using it — across the server/client boundary for a feature (rendering as a different element) that doesn't need runtime JS.

## Verification performed

- `test/unit/ui-primitives.test.tsx` (402 lines) — behavioral tests across the primitive set.
- `test/unit/ui-server-boundary.test.ts` — the boundary-list and token-discipline suites described above; extended in Phase 4 to cover `sidebar.tsx` and `page-container.tsx` as they were added/migrated.
- `npx tsc --noEmit` and `npm run build` clean at the end of the phase.

## Screenshots

None specific to this phase — primitives aren't independently user-visible until adopted by a page. See [phase-2-landing-page.md](phase-2-landing-page.md) onward for the first visual evidence of the system in use. A live reference page exists in the running app at `/design-system` (`app/design-system/`) showing every primitive and its variants together.

## Lessons learned

- Building the server/client boundary constraint into an automated, exhaustive test (every file in the directory must appear in exactly one of two lists) rather than a code-review checklist is what made it survive three subsequent phases of primitives being added (`PageContainer` in Phase 4) and one pre-existing file being pulled in (`sidebar.tsx`, also Phase 4) without drifting.
- Deciding *not* to add `class-variance-authority` or `@radix-ui/react-slot` were both instances of the same judgment call: prefer a few more lines of plain TypeScript over a dependency, when the dependency's main value (ergonomics) is small relative to its cost (bundle weight, or in Slot's case, an unwanted client-boundary crossing).

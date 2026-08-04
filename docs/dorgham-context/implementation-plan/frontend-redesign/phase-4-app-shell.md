# Phase 4 — Authenticated App Shell

**Status:** ✅ Complete — executed with full first-hand detail in the conversation this documentation set was written from.

## Goal

Make the authenticated application feel like the same product as the redesigned landing page and auth journey: same visual language, typography, spacing, colors, elevation, motion, and interaction patterns. Replace inconsistent, duplicated layout markup with design-system primitives. Improve information hierarchy, tablet/mobile responsiveness, and accessibility (keyboard navigation, focus management, ARIA) — without changing backend business logic, introducing new product features, or breaking existing functionality.

## Scope

`components/ui/sidebar.tsx` (full rewrite), a new `app/(app)/layout.tsx` shared shell, a new `PageContainer` primitive, and the outer wrapper markup of every authenticated page: chat, exam (hub/shell/results), profile, checklist, speaking history (list + detail). Explicitly out of scope: the *internal* content of exam's skill-card grid and the exam shell's timer/header chrome — those are page-specific product content, not shell chrome, and were left untouched per "prefer refactoring existing UI over rewriting logic."

## Research performed before any code changed

A structural audit of the existing app chrome found:

- **`components/ui/sidebar.tsx`** (397 lines) was the *only* chrome component — a monolith mixing mobile-drawer state, its own identity fetch (`useCurrentUser()`, issuing its own `GET /api/profile` on every page it mounted on — an accepted, documented duplication rather than a shared context), 10 hand-rolled inline SVG icon functions (none using `lucide-react`, despite that being used everywhere else in the app), and raw hex colors/`gray-*` classes throughout — none of it on the Phase 0–3 token system.
- **No shared header/topbar component existed anywhere.** The only "header" in the authenticated app was the sidebar's own mobile-only sticky bar, plus two page-local, hand-built `<header>` elements (`exam/shell`, `speaking/share/[token]`).
- **No route-group layout existed.** Every authenticated page independently imported `Sidebar` and wrapped it in its own `<div className="flex min-h-screen ..."><Sidebar/><main>...</main></div>` — `exam/results/page.tsx` repeated this wrapper **five times**, once per early return branch.
- **No global search or notifications UI existed anywhere** — confirmed by grep, not assumed.
- **No user menu or logout existed anywhere.** The sidebar's "User Badge" was avatar-initials + truncated email with zero click handler; a codebase-wide grep for `logout`/`signOut` returned nothing on the frontend. Investigating the Gateway found `POST /auth/logout` **already fully implemented** (blacklists the access token, clears cookies server-side) with nothing in the frontend ever calling it.
- **`middleware.ts`'s actual redirect-to-login guard is commented out** — protected routes are not currently enforced by middleware. Noted as a pre-existing gap, explicitly not fixed (it's authentication/authorization logic, out of this phase's scope).

## Architecture decisions

**Sidebar rewritten in place, not replaced with a new component**, to minimize risk: same 7 nav items, same exact-vs-prefix active-route matching, same disabled/"Soon" entries, same mobile drawer mechanics (translate-x transform, backdrop, body-scroll lock, close-on-route-change) — only the implementation (tokens, icons, primitives) changed, not the behavior.

**`app/(app)/layout.tsx` route group** — invisible in the URL — renders `<Sidebar/>` once and wraps `{children}` in a `min-w-0 flex-1` container. `chat`, `exam` (+ `shell`, `results`), `profile`, `checklist/[programId]`, and `speaking/history` (+ `[id]`) were moved into this group via `git mv`, preserving file history. `speaking/share/[token]` was deliberately **not** moved — it's an intentionally public, unauthenticated page with no sidebar, and moving it into `(app)` would have been wrong regardless of the route group being URL-invisible.

**New `PageContainer` primitive** (`components/ui/page-container.tsx`) extracts the `max-w-Nxl mx-auto p-8 md:p-12` pattern that eight pages each wrote slightly differently, into one sized primitive (`md`/`lg`/`xl`/`2xl`/`full` → `max-w-3xl` through `max-w-none`), added to the Phase 1 primitive barrel and to the automated server/client-boundary + token-discipline test suite.

**`exam/results/page.tsx`'s five duplicated wrapper blocks collapsed to zero** — each of its five early-return branches (loading, error, Reading-no-result, Writing-no-result, generic result) now returns only its content inside `PageContainer`; the Sidebar/flex wrapper is gone entirely, supplied once by the layout.

**`exam/shell/page.tsx`'s own `<Sidebar/>` import removed** — it was rendering a second sidebar instance nested inside what would now also be the layout's sidebar. The page's focus-mode full-height (`h-screen overflow-hidden`) chrome, its own header (module name, timer, submit button), and its two `fixed inset-0` overlays (evaluating state, submit-confirmation modal) were preserved exactly, restructured as a `<>...</>` fragment instead of the old wrapping `<div>` so they no longer depend on a `<Sidebar/>` sibling that no longer exists at that level.

**A pre-existing, deliberately-isolated exception left untouched**: `app/error.tsx` and `app/exam/error.tsx` still use raw hex/`gray-*` classes. This was a considered decision, not an oversight — both files are documented in their own comments as intentionally avoiding any design-system import, so they can still render a recoverable error screen even if the CSS/token layer itself is what crashed. Tokenizing them would work against that resilience guarantee, so they were left exactly as found.

## UI/UX decisions

- **Icons**: all 10 hand-rolled inline SVGs replaced with `lucide-react` icons via the existing `Icon` primitive (`MessageSquare`, `Target`, `ListChecks`, `GraduationCap`, `AudioLines`, `FileText`, `User`, `Sparkles`, `Menu`, `X`, `ChevronUp`, `ArrowRight`, `LogOut`), matching every other surface in the app.
- **Brand mark**: swapped the sidebar's own hand-written "G roundel + goa" markup for the shared `Wordmark` component Phase 2 built for the marketing navbar — the brand identity is now sourced from one place instead of two independently-maintained copies that could drift.
- **Colors**: every raw hex value (`#0d4d3a`, `#fbfbfa`, `#d8f3e5`, `#eaf7f0`, etc.) and every `gray-*` class replaced with semantic tokens (`bg-surface`, `bg-canvas-subtle`, `bg-brand-subtle`, `text-fg-muted`, etc.) — verified, not assumed: the sidebar is now included in the automated "no raw hex, no default gray ramps" test that previously excluded it by name.
- **New, working user menu**: a small self-contained dropdown (click-outside + Escape to close, `aria-haspopup="menu"`/`aria-expanded`) replacing the inert "User Badge," containing a Profile link and a Log out action. Log out calls the newly-wired `authApi.logout()` (pure frontend consumption of the Gateway's pre-existing, already-implemented `POST /auth/logout` — no backend change) and redirects to `/login`.
- **Content-level token cleanup** on the migrated pages: `profile`, `checklist/[programId]`, `speaking/history` (+ `[id]`), and `exam/results` had their ad hoc raw-hex banners/cards/badges replaced with `Alert`/`Card`/`Badge`/`Button`/`PageContainer` — same visual outcome, tokenized implementation. `exam/page.tsx` and `exam/shell/page.tsx`'s *internal* content (skill-card grid, gradient background, timer header) was deliberately left as-is — out of this phase's shell-only scope.
- **Print behavior preserved**: the checklist page previously wrapped only `<Sidebar/>` in a `print-hidden` div to keep chrome out of printed checklists. The new sidebar carries `print:hidden` on its own root elements instead, which is a strict improvement (every authenticated page's sidebar now correctly hides on print, not just checklist's) rather than a regression.

## Components introduced

`components/ui/page-container.tsx` (`PageContainer`). No other new primitives — this phase is chrome consolidation and adoption, not new primitive surface area (beyond `PageContainer`).

## Files created

- `services/frontend/app/(app)/layout.tsx`
- `services/frontend/components/ui/page-container.tsx`

## Files modified

- `services/frontend/components/ui/sidebar.tsx` (full rewrite)
- `services/frontend/components/ui/index.ts` (export `PageContainer`)
- `services/frontend/lib/api.ts` (added `authApi.logout()`)
- `services/frontend/test/unit/ui-server-boundary.test.ts` (added `sidebar.tsx` to `CLIENT_BY_DESIGN`, `page-container.tsx` to `MUST_BE_SERVER_RENDERABLE`; removed both files' prior exclusions from the "covers every primitive" and "design token discipline" checks now that they pass)
- `services/frontend/app/(app)/chat/page.tsx` (Sidebar wrapper removed, `h-screen overflow-hidden` behavior preserved on the page's own root)
- `services/frontend/app/(app)/profile/page.tsx` (wrapper removed, tokenized)
- `services/frontend/app/(app)/checklist/[programId]/page.tsx` (wrapper removed, tokenized, `print-hidden` div removed in favor of the sidebar's own `print:hidden`)
- `services/frontend/app/(app)/speaking/history/page.tsx` (wrapper removed, tokenized)
- `services/frontend/app/(app)/speaking/history/[id]/page.tsx` (wrapper removed, tokenized)
- `services/frontend/app/(app)/exam/page.tsx` (wrapper removed; internal gradient/card content preserved unchanged)
- `services/frontend/app/(app)/exam/shell/page.tsx` (Sidebar import/usage removed; internal header/timer/overlay content preserved unchanged, restructured as a fragment)
- `services/frontend/app/(app)/exam/results/page.tsx` (all 5 duplicated wrappers collapsed to `PageContainer`, tokenized)

## Files moved (via `git mv`, history preserved)

- `app/chat/` → `app/(app)/chat/`
- `app/profile/` → `app/(app)/profile/`
- `app/exam/` → `app/(app)/exam/` (including `shell/`, `results/`, and the pre-existing `error.tsx`, left content-unchanged)
- `app/checklist/` → `app/(app)/checklist/`
- `app/speaking/history/` → `app/(app)/speaking/history/` (`app/speaking/share/[token]/` deliberately left in place, outside the group)

## Accessibility improvements

- `aria-current="page"` added to the active nav link (previously absent — only 1 use of `aria-current` existed codebase-wide before this phase, per the origin audit).
- The new user menu is keyboard- and screen-reader-operable: `aria-haspopup="menu"`, `aria-expanded`, `role="menu"`/`role="menuitem"`, closes on Escape, closes on click-outside — none of which existed on the previous inert badge because there was no interactive control there at all.
- Nav landmark added (`<nav aria-label="Main">`) where the sidebar's navigation list previously had no explicit landmark role beyond the bare list markup.

## Performance improvements

Net code-size reduction, not addition: five duplicated wrapper blocks in `exam/results/page.tsx` alone collapsed into one shared layout; seven other pages' boilerplate wrapper markup removed the same way. No new dependencies were installed — `lucide-react` was already a dependency and already used everywhere else in the app; the sidebar rewrite is the one place it was *not* already used, and now is.

## Verification performed

- `npx tsc --noEmit`: clean.
- `npm run build`: succeeded, same 17 routes as before (the route group is URL-invisible, so route count and paths are unchanged).
- `npx vitest run`: **198/198 passing** (192 pre-existing + `PageContainer`/`sidebar.tsx` newly covered by the boundary/token-discipline suite, which now covers 100% of `components/ui/`).
- Manual Playwright screenshots across desktop (1280px), tablet (820px), and mobile (390px) viewports of: chat, exam hub, profile, speaking history, checklist, exam/shell, exam/results, the mobile drawer open, and the user menu open — visually confirmed no double-sidebar regression from the file moves, correct active-state highlighting on every route, and a consistent visual language with the landing page.
- **One incidental, disclosed operational finding**: a live dev server on port 3000 held a file lock that blocked `git mv` on three of the five directories being moved. Stopped with explicit user go-ahead (asked first, via `AskUserQuestion`, rather than assumed) before proceeding — documented here because it's the kind of environmental surprise a future engineer repeating a similar large file-move should expect and plan around.

## Screenshots

Captured during this phase (desktop/tablet/mobile, 10 shots covering every redesigned screen plus interactive states) via a temporary Playwright script against a local production build on port 3100; not committed to the repository (verification artifacts in a scratch directory). As with Phase 3, re-capturing and committing a durable screenshot set is a reasonable Phase 6 task if permanent visual documentation is wanted.

## Lessons learned

- A "shell redesign" phase needs an explicit research pass *before* any code changes — the discovery that `POST /auth/logout` already existed and was simply never called (exactly the same shape as Phase 3's `forgot-password` discovery) would not have been found by assuming logout needed a new backend endpoint and either building one out-of-scope or shipping a fake logout button.
- Deliberately *not* touching `app/error.tsx`/`app/exam/error.tsx` despite them visibly violating the token-discipline rule everywhere else is the correct call, not an inconsistency to "clean up" later — their raw-hex/no-imports pattern is a documented resilience decision (render even if the token layer is what broke), and a phase's job is to recognize when a rule has a deliberate, documented exception rather than applying it uniformly.
- Route-group moves (`git mv` across directories) are risky against a live dev server holding file locks on Windows — worth flagging explicitly to whoever repeats a similar directory restructuring, and worth checking `netstat`/running processes *before* attempting the move rather than after the first failure.

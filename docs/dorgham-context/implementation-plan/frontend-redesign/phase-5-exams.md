# Phase 5 — Exams, Chat & Practice Surfaces, and States

**Status:** 📋 Planned, not started.

This is a forward-looking implementation plan, written so a new engineer can execute it without needing the rest of this conversation for context. It assumes Phases 0–4 are complete: the token system, the full `components/ui/*` primitive library (`Button`, `Card`, `Badge`, `Alert`, `Field`/`Input`/`Select`/`Textarea`, `Modal`, `Tabs`, `Progress`, `Skeleton`, `EmptyState`, `PageContainer`, etc. — see [phase-1-design-system.md](phase-1-design-system.md)), and the app shell (`app/(app)/layout.tsx` + the rebuilt `Sidebar`) all exist and are in use.

## Goal

Phase 4 unified the *chrome* around chat, exam, reading, writing, and speaking (sidebar, layout, page containers) but explicitly left their *internal* content untouched. This phase finishes the job: bring the actual product surfaces — where GOA's core value is delivered — onto the design system, and close the "no designed loading/empty/error state" gap the original audit found app-wide (`test/unit` currently has no `loading.tsx` files and no `not-found.tsx` anywhere in `app/`).

## Scope

- `app/(app)/exam/page.tsx` (hub) — internal content only; the shell wrapper is already done.
- `app/(app)/exam/shell/page.tsx` — internal header/timer/workspace chrome; the shell wrapper and overlay structure are already done.
- `app/(app)/exam/results/page.tsx` — verify the Phase 4 tokenization is complete; this phase's job here is mostly already done, confirm and close any gaps.
- `components/reading/*` (`PassagePanel`, `QuestionNavSidebar`, `ReadingExam`, `SectionTabs`, `SubmitConfirmModal`, `questions/`, `results/`)
- `components/writing/*` (`CombinedWritingResults`, `StimulusPanel`, `TaskResultCard`, `WritingExam`, `WritingTaskPanel`)
- `components/speaking/*` (`band-trend-chart`, `evaluation-breakdown`, `inline-alert`, `mic-button`, `recording-timer`, `session-history-item`, `session-history-list`, `share-button`, `status-chip`, `waveform-canvas`)
- `components/chat/*` (`chat-shell`, `chat-input`, `message-bubble`, `message-list`, `streaming-message`, `typing-indicator`, `essay-composer`, `essay-highlighter`, `sources-footnote`, `speaking-session-panel`, `writing-evaluation-panel`)
- App-wide: `EmptyState` adoption, `loading.tsx` per authenticated route, a global `not-found.tsx`, consolidation of any remaining hand-rolled error banners onto `Alert`.

Out of scope: any backend/API contract change, any new exam skill or product feature, checklist and profile (those are Phase 6).

## Why this order (exams/chat before checklist/profile)

Per the original plan's impact ranking (§15 of the origin document): exam surfaces are "core product value... behind auth and lower traffic [than landing/auth]" but still ranked above checklist/profile, which are lower-traffic still. Chat is "already the most polished surface; mostly retinting + mobile" — grouped into this phase because it shares the same practice-surface visual language (message bubbles, streaming states, evaluation panels) as writing/speaking, and because the states work (empty/loading/error) benefits from being done once across all of these surfaces together rather than piecemeal.

## Architecture decisions to make (not yet decided — this phase's first task)

**Three visual palettes still need reconciling into one.** The original audit (§0.1) identified: landing+auth (now tokenized, Phase 2–3), the app shell (now tokenized, Phase 4), and **chat + speaking, which used a third, bespoke green-gray palette** (`#1D291E`, `#526053`, `#E8ECE7`, `#F2F5F1`, `#0D3820`) that has not yet been touched. This phase is where that third palette gets retired onto the `sage`/`forest` tokens. Reading and writing were not called out with their own bespoke palette in the audit but should be verified against the token-discipline test as this phase touches them.

**`EmptyState` primitive adoption strategy.** Decide, before writing any page: does every list/collection surface (speaking session history when empty, chat with no messages yet, exam progress with no completed exams) get its own copy via `EmptyState`'s props, or does each domain get a thin wrapper component (e.g., `SpeakingHistoryEmptyState`) that calls `EmptyState` with fixed copy? Recommendation: use `EmptyState` directly with inline props at each call site unless the same empty state is needed in 2+ places — mirrors the "don't build abstractions for a single use" principle already established in this codebase's own conventions.

**`loading.tsx` skeletons must match real layout, not be generic spinners.** The origin plan (§8) is explicit: "route-level `loading.tsx` with skeletons matching real layout." For each authenticated route, the `loading.tsx` file should use the `Skeleton`/`SkeletonGroup` primitives shaped to approximate that route's actual content (e.g., `exam/results/loading.tsx` should render skeleton blocks matching the result-banner + section-grid shape, not a single centered spinner) — this is exactly the pattern `exam/results/page.tsx`'s own `loading` state already partially does inline (see Phase 4's file); the job here is to extract it to the file-convention `loading.tsx` so Next.js's streaming/Suspense boundary shows it automatically during navigation, not just during in-page data fetching.

## UI/UX plan by surface

### Exam hub (`app/(app)/exam/page.tsx`)
Currently: a 437-line page with a custom `bg-linear-to-br from-emerald-50 via-white to-orange-50` gradient background, skill cards with inline SVGs and raw hex bgColors (`bg-[#e2f4ea]`, `bg-[#faedd4]`, `bg-[#f2e7f7]`, `bg-[#e3edf7]`), and hand-rolled buttons/badges. Plan:
- Retire the emerald-to-orange gradient in favor of the token system's canvas/subtle rhythm, consistent with how the landing page's sections alternate (Phase 2).
- Rebuild the 4 skill cards on `Card` (`variant="interactive"` for the "Take Exam" affordance) with `Icon`/lucide replacing the inline SVGs, and `Badge` for the "Coming soon" state — unifying with the sidebar's own "Soon" treatment from Phase 4, per the origin plan's explicit note that these two should match.
- Resume-session banner and profile-load-error banner → `Alert`.
- Overall-band summary card → tokenized `Card`, but treat the band score itself as *data emphasis* per the origin plan §12: "Scores, match percentages, and band results are the emotional payload of this product... they get dedicated display-scale treatment" — use `Heading`/large serif numerals, not body-text weight.

### Exam shell (`app/(app)/exam/shell/page.tsx`)
Currently: focus-mode full-height layout (correctly preserved by Phase 4), with its own raw-hex header (timer chip, submit button), a `md:hidden` "EXAM MODE LOCKED" overlay, and two `fixed inset-0` overlays (evaluating spinner, submit-confirmation modal). Plan:
- Header timer chip → tokenized, with the existing critical-time red-pulse state preserved but recolored onto `danger` tokens.
- Submit button and submit-confirmation modal's two buttons → `Button` primitive; the confirmation modal itself → `Modal`/`ModalContent` (Radix-backed, gets a real focus trap for free — currently a hand-rolled `fixed inset-0` div with no focus management, which is an accessibility gap specific to this component).
- The `md:hidden` "desktop required" lockout screen → tokenized but content/logic unchanged (it's a genuine product constraint, not a redesign target).
- **Mobile passage/questions split is a known, documented gap** (origin plan §10: "Exam shell's `w-1/2` + `w-1/2` split has no mobile treatment... two unusable 180px columns"). This phase should decide whether to build the tabbed passage/questions view the origin plan proposes, given the shell already enforces desktop-only for exam-taking — recommend confirming with product whether mobile exam-taking is actually a target before investing in this, since the deliberate "EXAM MODE LOCKED" desktop gate suggests it may not be.

### Reading (`components/reading/*`)
- `PassagePanel`/`QuestionNavSidebar`/`SectionTabs` → tokenize; `QuestionNavSidebar`'s fixed `w-44` rail (origin plan §10) should get a collapse affordance or convert to the same responsive pattern chosen for the exam shell's mobile story.
- `SubmitConfirmModal` → migrate onto the `Modal` primitive (currently has its own hand-rolled confirm dialog, separate from the exam shell's — both should end up as `Modal` consumers, closing two hand-rolled dialogs at once).
- `results/` (Reading results view) → verify tokens; this feeds into `exam/results/page.tsx`, which Phase 4 already tokenized at the wrapper level.

### Writing (`components/writing/*`)
- `WritingExam`, `WritingTaskPanel`, `StimulusPanel`, `TaskResultCard`, `CombinedWritingResults` → tokenize. `CombinedWritingResults` in particular feeds `exam/results/page.tsx`'s Writing branch and should get the same "data emphasis" treatment as the generic result branch (large serif band score).

### Speaking (`components/speaking/*`)
- Per the origin plan §8: "speaking waveform + mic button already good — align colors only." `waveform-canvas.tsx` and `mic-button.tsx` are explicitly *not* candidates for structural rework, only token migration — preserve their existing interaction design.
- `evaluation-breakdown`, `band-trend-chart`, `session-history-item`/`-list`, `status-chip`, `inline-alert` → tokenize; `inline-alert.tsx` specifically should be evaluated for retirement in favor of the shared `Alert` primitive (it was called out in the origin audit §7.4 as one of three duplicate error-banner implementations `Alert` was built to absorb — the other two, in `profile/page.tsx` and `ChecklistView.tsx`, were already migrated as part of Phase 3/4's incidental cleanup; this is the one still outstanding).

### Chat (`components/chat/*`)
- Retint `message-bubble`, `streaming-message`, `typing-indicator`, `chat-input` onto tokens, retiring the bespoke green-gray palette.
- Empty state (no messages yet) → `EmptyState` with suggested-prompt affordances, replacing whatever currently renders (verify current behavior before assuming one exists — the origin audit did not confirm one does).
- Mobile layout: origin plan §10 flags "Chat uses fixed `px-8` on the shell and its input row; below 400px this leaves very little content width" — convert to responsive padding (`px-4 sm:px-6 md:px-8`).
- Header's 3 actions (visible in the Phase 4 screenshots as "New conversation," "Forget what you know about me," a sync-status chip) need a mobile overflow menu per the origin plan — likely reusing the same dropdown-menu pattern built for the Phase 4 sidebar's user menu (click-outside + Escape, `aria-haspopup`), rather than inventing a second pattern.
- `essay-composer`/`essay-highlighter`/`writing-evaluation-panel`/`speaking-session-panel` are chat-embedded practice surfaces — tokenize consistent with the standalone writing/speaking treatment above so the in-chat and standalone versions don't diverge.

### App-wide states
- Add `app/(app)/loading.tsx` and per-route `loading.tsx` files (at minimum: `exam/loading.tsx`, `exam/shell/loading.tsx`, `exam/results/loading.tsx`, `speaking/history/loading.tsx`) using `Skeleton`/`SkeletonGroup` shaped to each route's real layout.
- Add a global `app/not-found.tsx` (currently absent entirely) — tokenized, with a way back to `/chat`, consistent with the existing `app/error.tsx`'s recovery-action pattern but *not* subject to the same "must render even if tokens are broken" constraint, since a 404 is a routing outcome, not a runtime crash — it's safe to build this one fully on the design system.
- Sweep for any remaining hand-rolled error banners not yet on `Alert` (speaking's `inline-alert.tsx`, noted above, is the last confirmed one from the original audit's list of three).

## Reusable components

No new `components/ui/*` primitives are anticipated for this phase — everything needed (`Card`, `Alert`, `Modal`, `Badge`, `Skeleton`/`SkeletonGroup`, `EmptyState`, `Progress`, `Tabs`) already exists from Phase 1. If a genuinely new pattern emerges (e.g., a "question nav rail" component reused between reading and a future listening exam), build it as a domain component in `components/exam/` or `components/reading/`, composed from primitives — not as a new `components/ui/*` primitive, since it carries exam-domain knowledge and primitives must not.

## Accessibility goals

- Exam question navigation (reading, and any future skill) should be arrow-key navigable, per the origin plan §11.4 — currently not confirmed either way; audit and fix as part of this phase.
- Chat streaming, exam timer warnings (the critical-time state), and save confirmations should announce via `aria-live` — the origin audit found only 2 `aria-live` uses codebase-wide before Phase 0; verify how many exist now and close remaining gaps in these specific surfaces.
- No keyboard traps in the chat composer — verify explicitly, since streaming/typing-indicator UI is a common place for focus to get silently stolen.
- Icon-only buttons across all these surfaces (mic button, share button, print button, chevrons) need `aria-label` per the `Icon`/`Button` primitive's own established convention (`iconOnly` requires `aria-label` at the type level when using the `Button` primitive) — anywhere a hand-rolled icon button still exists outside that primitive should be migrated or given the same treatment directly.
- Contrast: origin audit flagged `text-gray-400` on white (~2.8:1, fails AA) used for metadata specifically "across profile, reading, and chat" — reading and chat are in this phase's scope; confirm this has been replaced with `text-fg-subtle` (6.0:1, passes AA per `docs/DESIGN-TOKENS.md`) everywhere it appears in these surfaces.

## Responsive behavior

- Reading nav rail: fixed `w-44` needs a collapse affordance below `lg`.
- Exam shell passage/question split: decide (per Architecture note above) whether a mobile tabbed view is built, or whether the existing desktop-only gate is confirmed as the permanent product decision and documented as such instead.
- Chat: fixed `px-8` → responsive padding; header overflow menu below the breakpoint where all 3 actions no longer fit inline.
- Speaking waveform/recording UI: verify at 320/375px — origin plan doesn't flag a specific known issue here, so this is a verification task, not a known fix.
- All touch targets ≥ 44×44px (origin plan §10) — audit icon buttons and chips in these surfaces specifically, since several pre-redesign chips were `py-1.5` (~28px).

## Verification strategy

1. `npx tsc --noEmit` and `npm run build` clean, as with every prior phase.
2. `npx vitest run` — extend `test/unit/ui-server-boundary.test.ts`'s coverage only if new `components/ui/*` primitives are added (none anticipated); existing domain-level tests (`test/unit/writing-exam.test.ts`, `writing-stream.test.ts`, `checklist-*.test.ts`, `essay-highlighter.test.tsx`) should continue passing unmodified unless copy/markup they assert on changes, in which case update them in the same commit per the origin plan's §0.9 refactor-risk note.
3. e2e specs most likely affected: `test/e2e/exam-flow.spec.ts`, `reading-exam.spec.ts`, `writing-exam.spec.ts`, `writing-system.spec.ts`, `speaking-history.spec.ts`, `speaking-history-mocked.spec.ts`, `speaking-system.spec.ts`, `chat-system.spec.ts` — review each for `getByText`/`data-testid` coupling to markup or copy this phase changes, per the same §0.9 discipline every prior phase followed.
4. Manual Playwright screenshots (desktop + tablet + mobile) of every touched surface, following the pattern established in Phases 3–4: a temporary script against a local production build, visually inspected before claiming completion — not just a passing test suite.
5. Re-run the Lighthouse gate (`test/seo/lighthouse.spec.ts`) if it's extended to cover `/chat` or `/exam` per the origin plan's stated intent (§13); confirm current gate scope before assuming it already covers these routes.

## Acceptance criteria

- No raw hex literals or `gray-*`/`slate-*`/`zinc-*`/`neutral-*`/`stone-*` classes remain in any file under `components/chat/`, `components/reading/`, `components/writing/`, `components/speaking/`, `components/exam/`, or the exam-related `app/(app)/exam/**` page files (verifiable by extending the token-discipline scan pattern from `test/unit/ui-server-boundary.test.ts` to these directories, or by manual grep as a verification step).
- Every authenticated route with a data-fetching delay has a `loading.tsx` whose skeleton shape approximates its real content.
- A global `not-found.tsx` exists and is tokenized.
- No more than one hand-rolled error-banner pattern remains outside `Alert` (target: zero, matching the origin plan's full-absorption intent).
- All existing e2e and unit tests pass, with any copy/selector-coupled tests updated in the same change as the markup that broke them, never left red.
- Manual visual verification (screenshots) confirms visual consistency with the already-shipped landing/auth/app-shell surfaces — not just "uses tokens" in code, but reads as the same product when actually rendered.

# Phase 3 — Auth + Onboarding

**Status:** ✅ Complete — executed with full first-hand detail in the conversation this documentation set was written from.

## Goal

Rebuild the entire pre-chat user journey — Register, Login, Forgot Password, Reset Password, Verify Email, and the Onboarding wizard — to the same design-system quality as the Phase 2 landing page, closing both a major accessibility gap (zero `aria-describedby` usage in any auth form) and two functional bugs discovered during the audit: `ResetPasswordForm` called the wrong backend endpoint for its "send me a link" step, and the onboarding wizard's `handleFinish` discarded all collected data instead of persisting it.

## Scope

`app/(auth)/*` (new route group), `app/onboarding/*`, `components/auth/*`, `components/onboarding/*`, `lib/api.ts`. One narrow, explicitly pre-authorized exception to the "frontend only" rule: a single Gateway routing addition (`PUT /api/profile`), justified below.

**Explicit constraint from the approval that scoped this phase:** no backend business logic, validation, database behavior, or user-service implementation changes — the Gateway change was authorized only as a routing/proxy addition exposing an endpoint the User service already implemented.

## What the backend already supported (confirmed by reading `services/gateway` + `services/user` before writing any frontend code)

| Step | Endpoint | Status found |
|---|---|---|
| Register | `POST /users` | Frontend already called this correctly. |
| Login | `POST /auth/login` | Frontend already called this correctly. |
| Request password reset email | `POST /auth/forgot-password` | Existed on the backend; **nothing in the frontend called it.** |
| Confirm reset with token | `POST /auth/reset-password` with `{token, newPassword}` | Existed end-to-end; **`ResetPasswordForm` was calling this same path for the wrong step** (its "send email" button), meaning nowhere in the app could a user actually set a new password. |
| Verify email | `GET /auth/verify-email/:token` | Existed end-to-end; registration already triggered the email server-side, but no frontend page existed to land the link on. |
| Onboarding profile fields | `PUT /users/:id/profile` (User service) | DTO and service logic existed; **not proxied through the Gateway** — only `GET /api/profile` was. |
| Onboarding CV upload | `POST /api/writing/cv/upload` | Existed and was real (used by the writing/CV-review feature) — reusable as-is. |

Net effect: five of six auth steps were buildable end-to-end with zero backend changes. Onboarding's profile-field persistence needed the one Gateway proxy route, which is the only place this phase touched anything outside `services/frontend`.

## Architecture decisions

**Route group for shared auth chrome.** `app/(auth)/layout.tsx` — a route group, so URLs are unchanged — renders a split-screen shell: a dark forest brand panel (same visual language as the landing page's CTA/footer) on `lg+`, collapsing to a compact top band below that; the form card sits on the other side. This replaced three pages independently copy-pasting the same gradient-card layout.

**Route map changed to match what the backend endpoints actually do**, not just added pages:
```
/register                    existing, rebuilt
/login                       existing, rebuilt
/forgot-password             NEW — request step (email only)
/reset-password?token=...    rebuilt — becomes the CONFIRM step, reading the token from the URL
/verify-email/[token]        NEW — lands the email link
/onboarding                  existing, rebuilt — 4 steps + real persistence
```
`/reset-password` changes meaning from "request" to "confirm" because that's what the backend endpoint at that path actually does; the request step moves to the new `/forgot-password`, matching the backend's own naming. Login's "Forgot password?" link was repointed accordingly.

**Gateway proxy (`services/gateway/handlers/profile.go`, `UpdateProfile`)** — reads the user id from the JWT via the existing `authenticatedUserID(c)` helper (never from the client-supplied body), forwards the request body verbatim to `PUT {userServiceURL}/users/{userID}/profile` with the internal API key header, and streams the upstream status/body straight back. Written as an exact pattern-match against the already-tested `GetProfile` handler in the same file. Route registered in `server.go` immediately after the existing `GET /profile` route. Five new Go tests added in `profile_test.go` mirroring `GetProfile`'s test style (auth required, id always from JWT never client-supplied, body forwarded, upstream error propagated).

**Onboarding wizard step state synced to the URL** (`?step=N`) rather than kept only in component state, so a refresh or back/forward navigation doesn't silently reset progress.

## UI/UX decisions

- **Register/Login**: rebuilt on `Field`/`Input`/`Button`/`Alert`. Added a password-visibility toggle, a real success moment on Register before redirecting (previously silent), and backend error messages surfaced on Login instead of one hardcoded string.
- **Forgot Password (new)**: single email field; success state deliberately does not reveal whether the address exists — copy reads "if that account exists," matching the backend's own non-revealing response, with a resend affordance after a cooldown.
- **Reset Password (confirm)**: reads `token` from the URL; states for missing/malformed token (shown immediately, no submit), the new-password + confirm form with inline match checking, loading, success, and an invalid/expired-token error distinguished from a generic failure.
- **Verify Email (new)**: calls the verify endpoint on mount; states for verifying (spinner), success, and expired/invalid.
- **Onboarding stepper**: replaced a manual percentage-width bar with a real `OnboardingStepper` (completed/current/upcoming states) built on the `Progress` primitive, collapsing to a compact "Step X of 4" + bar on mobile.
- **Onboarding CV upload step**: replaced an entirely simulated `simulateUploadAndProcessing()` (fake progress bar, fake "processing" spinner, no network call at all) with a real call to `POST /api/writing/cv/upload`, real upload progress, upfront file type/size validation (replacing a browser `alert()`), a cancel affordance, and — because this route is paid-tier-gated on the backend (`subscriptionMiddleware.RequirePaid`) — a specific, honest "CV review is part of the paid plan, you can skip this for now" state when the Gateway returns its `subscription_required` 403, rather than a generic failure message.
- **Onboarding persistence (the actual bug fix)**: `handleFinish` now calls `authApi.updateProfile()` against the new Gateway route, shows a loading state on the final step's submit, and — critically — keeps the user's answers on screen if the request fails, rather than discarding a completed wizard on a network error the way the pre-existing stub silently did (it never even attempted a save).
- **Honest disclosure of a schema gap, not a silent drop**: `UpdateProfileDto` on the backend has no field for university name, graduation year, or target degree/major/intake — only degree level, GPA(+scale), IELTS score, field of study, ECTS, work experience, and target countries. Those wizard fields stay in the UI (still useful context in the moment) but are explicitly documented as not persisted in `buildProfilePayload`'s code comment, rather than either fabricating a backend field or silently dropping the data without disclosure.

## Components introduced

`components/auth/auth-card.tsx` (shared `AuthCard({title, subtitle, children})`), `components/auth/ForgotPasswordForm.tsx` (new), `components/auth/VerifyEmailStatus.tsx` (new), `components/onboarding/types.ts`, `components/onboarding/onboarding-stepper.tsx`, `components/onboarding/choice-card.tsx`.

## Files created

- `services/frontend/app/(auth)/layout.tsx`
- `services/frontend/app/(auth)/register/page.tsx`
- `services/frontend/app/(auth)/login/page.tsx`
- `services/frontend/app/(auth)/forgot-password/page.tsx`
- `services/frontend/app/(auth)/reset-password/page.tsx`
- `services/frontend/app/(auth)/verify-email/[token]/page.tsx`
- `services/frontend/components/auth/auth-card.tsx`
- `services/frontend/components/auth/ForgotPasswordForm.tsx`
- `services/frontend/components/auth/VerifyEmailStatus.tsx`
- `services/frontend/components/onboarding/types.ts`
- `services/frontend/components/onboarding/onboarding-stepper.tsx`
- `services/frontend/components/onboarding/choice-card.tsx`
- `services/frontend/test/unit/auth-onboarding.test.tsx` (9 tests)

## Files modified

- `services/frontend/lib/api.ts` (rewritten: added `apiErrorMessage`, `isSubscriptionRequired` helpers, `UpdateProfilePayload` type, the full `authApi` object with named methods)
- `services/frontend/components/auth/RegisterForm.tsx`, `LoginForm.tsx`, `ResetPasswordForm.tsx` (rewritten)
- `services/frontend/components/onboarding/AcademicStep.tsx`, `LanguageStep.tsx`, `TargetStep.tsx`, `CvUploadStep.tsx` (all rebuilt)
- `services/frontend/app/onboarding/page.tsx` (rewritten: URL-synced step, `buildProfilePayload()`, `Suspense`-wrapped wizard, real `handleFinish`)
- `services/frontend/test/e2e/fe-integration.spec.ts` (FE-01/FE-03 updated with new selectors and mocks)
- `services/gateway/handlers/profile.go` (added `UpdateProfile` handler)
- `services/gateway/server.go` (registered `PUT /api/profile`)
- `services/gateway/handlers/profile_test.go` (5 new tests)

## Files deleted

- `services/frontend/app/login/page.tsx`, `app/register/page.tsx`, `app/reset-password/page.tsx` (superseded by the `(auth)` route group equivalents)

## Accessibility improvements

- Every rebuilt form now wires `aria-describedby`/`aria-invalid`/`role="alert"` via `Field`, closing the exact gap the origin audit flagged as the largest in the codebase — previously auth forms rendered errors as unassociated `<p>` tags with no screen-reader announcement of a failed submit.
- `Alert`'s `announce` convention applied deliberately: the invalid-reset-token state uses `announce="none"` because it's static content present on page load, not a dynamic change — verified against the component's own documented convention rather than defaulting to `role="alert"` everywhere.
- `Progress`'s `role="progressbar"` + `aria-valuenow`/`aria-valuemax`/`aria-valuetext` used for the onboarding stepper instead of a purely visual bar.

## Performance improvements

Not separately measured as a distinct metric in this phase (the primitives themselves are already optimized per Phase 1); the practical impact was `npm run build` succeeding with 17 routes total and no new heavy dependencies introduced.

## Verification performed

- `npx tsc --noEmit`: clean.
- `npm run build`: succeeded, 17 routes.
- `npx vitest run`: 191/191 passing across 13 files (182 pre-existing + 9 new).
- Real Playwright screenshots of all 6 flows (Register, Login, Forgot Password, Reset Password, Verify Email, Onboarding) in both desktop and mobile viewports, visually inspected to confirm the intended split-screen/stepper design was actually achieved rather than assumed from code.
- **Explicit verification gap disclosed rather than hidden**: the Go toolchain was unavailable in the execution environment, so `services/gateway`'s new handler and its 5 tests could not be compiled or run. The code was written by exact pattern-match against the already-tested `GetProfile` handler, but this was not executed — flagged plainly in the phase completion report rather than claimed as a green test run.

## Screenshots

Captured during this phase (desktop + mobile, all 6 flows) via a temporary Playwright script; not committed to the repository (they were verification artifacts in a scratch directory, not permanent documentation assets). Re-capturing screenshots for permanent reference is a reasonable Phase 6 polish-sweep task if durable visual documentation is wanted.

## Lessons learned

- Reading the actual backend routes and DTOs *before* writing any frontend code is what surfaced both real bugs in this phase (`ResetPasswordForm` hitting the wrong endpoint; onboarding's Gateway proxy gap) — neither would have been found by only looking at the frontend in isolation.
- A completed multi-step wizard whose final action can fail must never discard the user's input on that failure — `handleFinish`'s original stub didn't even have this problem in the "hard" sense (it never called the network at all), but the fix had to actively decide to keep data on-screen on failure, which is an easy behavior to get backwards under time pressure (clear-then-redirect is the more "obvious" naive implementation).
- When a wizard collects data the backend genuinely cannot store yet (the university/gradYear/target-degree fields), the honest move is to say so in code (a comment documenting exactly what's dropped and why) rather than quietly wiring nothing and leaving a future reader to rediscover the gap by reading the DTO themselves.

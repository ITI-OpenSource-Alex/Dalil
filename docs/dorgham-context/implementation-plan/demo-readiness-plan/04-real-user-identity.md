# 04 — Real User Identity Wiring

## Objective

Replace every hardcoded placeholder user identity (`"user-lina"`,
`"session-lina-123"`, the hardcoded exam UUID
`00000000-0000-0000-0000-000000000001`, and the "Lina Ahmadi" persona shown
in the UI) with the actual logged-in user's identity, sourced from the
existing `useCurrentUser()` hook.

## Background

`chat-shell.tsx` sends a hardcoded `userId: "user-lina"` and
`sessionId: "session-lina-123"` on every chat request. `app/exam/page.tsx`
sends a hardcoded `userId: "00000000-0000-0000-0000-000000000001"` on every
exam session creation. `components/ui/sidebar.tsx` renders a static "LA /
Lina Ahmadi / lina.ahmadi@goa.app" badge regardless of who is logged in.

This single class of defect causes three separate visible failures:

1. Opportunity matching errors, because `local_user_profiles.user_id` is a
   UUID column and `"user-lina"` is not a valid UUID (see
   [03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)).
2. Speaking sessions are recorded against a phantom user rather than the
   person actually presenting.
3. Exam sessions are created under a user id that does not match the
   logged-in JWT — which the gateway's `examOwnership` middleware is
   designed to reject on submit, meaning a candidate could answer a full
   Reading exam and then get a 403 at the worst possible moment.

It is also the direct cause of a credibility problem: a reviewer who
registers under their own name and then sees the chat header say "Lina
Ahmadi • CGPA 3.45 • IELTS 6" will reasonably ask why.

The fix is largely mechanical: `useCurrentUser()` already exists, is
already correctly wired to `GET /api/profile` (which the gateway resolves
from the JWT — no id needs to be passed from the client), and is currently
consumed only by `/profile`. This task extends its use to the other
consumers.

## Why This Matters

This is the connective tissue underneath two other Critical-priority demo
blockers. Fixing it is what makes the opportunity-matching seed
(document 03) actually verifiable, and it removes the single most visible
"this is obviously a mockup" signal in the entire application — a stranger's
name and stats displayed to whoever just logged in.

## Scope

**In scope:**
- `chat-shell.tsx`: real user id and a derived, stable session id.
- `app/exam/page.tsx`: real user id for exam session creation, with a
  loading guard.
- `app/speaking/history/page.tsx`: real user id for history lookups.
- `components/ui/sidebar.tsx`: real email/initials in the account badge.
- Gating outbound requests (chat send, exam start) until the profile has
  actually resolved, so no request can race the fallback value out the door.

**Out of scope:**
- Fixing speaking-history's server-side user scoping (a documented,
  separate, auth-less limitation of the speaking service itself).
- Building a shared context/provider to deduplicate the resulting multiple
  `useCurrentUser()` calls across pages that all render the sidebar — accept
  the duplicate, cheap, cached GET behind the gateway for now; note the
  provider refactor as later cleanup, not demo-prep.
- Deleting `lib/current-user.ts` — it remains as an explicit fallback.

## Files Expected to Change

```
services/frontend/components/chat/chat-shell.tsx
services/frontend/app/exam/page.tsx
services/frontend/app/speaking/history/page.tsx
services/frontend/lib/current-user.ts
services/frontend/components/ui/sidebar.tsx
```

`services/frontend/app/hooks/useCurrentUser.ts` is read-only in this task —
no functional change expected, only confirm its existing contract
(`user`, `status`, `error`, `retry`) is sufficient for all four consumers
above.

## Detailed Implementation Plan

**Chat shell.** Replace `const [userId] = useState(CURRENT_USER_ID)` with
the hook's `user?.id`, falling back to `CURRENT_USER_ID` only while
`status === "loading"` or on error. Critically, **gate the first outbound
request**: `handleSendMessage` must not be reachable until
`status !== "loading"` — otherwise the very first message a user sends can
race the profile fetch and go out carrying the fallback id regardless of
this fix. The simplest correct implementation is disabling the send button
and the mic/pen toolbar buttons while the profile is loading; this doubles
as a legitimate, honest loading state rather than an awkward restriction.

Derive `sessionId` deterministically from the resolved user id (e.g. a
stable `chat-{userId}` string) instead of the hardcoded literal, computed
once via `useMemo` keyed on the user id so it only changes when the profile
actually resolves. The existing mount-time history-loading effect already
depends on `sessionId`, so history reloads correctly for the real user with
no further change needed there.

**Exam page.** Replace the hardcoded UUID with the hook's resolved user id.
Guard `startExam` so that it early-returns with a visible inline message
(not a silent no-op) if the id is not yet available. This matters more here
than in chat: an exam session created under the wrong user id will pass
creation successfully and then **fail at submit time** via
`examOwnership.Validate` on the gateway — a failure mode that would only
surface after a candidate has already answered a full exam, which is far
worse than failing fast at creation.

**Speaking history page.** Swap `CURRENT_USER_ID` for the hook's real id,
using the same loading gate. The page already has a loading skeleton
(`HistoryLoadingSkeleton`) — route the hook's `loading` status into that
existing UI rather than introducing a second loading treatment.

**Sidebar.** Replace the hardcoded "LA / Lina Ahmadi / lina.ahmadi@goa.app"
badge with the real email (from the hook) and initials derived from it.
Note that the sidebar renders on `/chat`, `/exam`, `/exam/shell`,
`/exam/results`, `/profile`, `/speaking/history`, and `/checklist/*` — this
change therefore issues a `GET /api/profile` call on every one of those page
loads. This is an accepted tradeoff for this task (a cheap, cached GET
behind the gateway); do not attempt to eliminate the duplication with a
context provider under demo-prep time pressure.

**`lib/current-user.ts`.** Do not delete this file or its export. Retarget
its doc comment to describe `CURRENT_USER_ID` explicitly as a fallback value
used only while a real profile is loading or unavailable, not as the primary
source of truth. Several other call sites (e.g., speaking WebSocket
construction) read from it — leaving the export in place minimizes the
blast radius of this change.

## Edge Cases

- Unauthenticated users currently can reach `/chat` (the auth middleware
  guard is disabled — see the corresponding Phase 2 task). With this
  change, such a user will see the fallback identity and a failed profile
  fetch; ensure the header and sidebar render something visually neutral in
  that state rather than continuing to say "Lina Ahmadi," which would be
  worse than the current behavior in a different way.
- Logging out and logging back in as a different account must update every
  displayed identity surface without requiring a hard page refresh — verify
  this explicitly, since some of these values (notably the derived
  `sessionId`) are memoized.
- If the profile fetch fails for a reason other than "not logged in" (e.g.,
  a transient gateway error), the loading gate should not permanently
  disable chat/exam — surface the hook's existing `retry` affordance rather
  than leaving the user stuck.

## Acceptance Criteria

- No hardcoded user id or session id literal remains as the **primary**
  value sent in `chat-shell.tsx` or `app/exam/page.tsx` (the fallback
  constant may remain as a degraded-state value only).
- The chat header, sidebar badge, and avatar initials all reflect the
  logged-in account's real email.
- Send, mic, and pen controls are disabled until the profile resolves.
- An exam session created from `/exam` submits successfully without a 403
  from `examOwnership`.
- Logging out and back in as a different user changes every displayed
  identity surface without a hard route refresh.

## Verification Steps

1. Register two distinct accounts, A and B.
2. Log in as A. Confirm `/chat`'s header, the sidebar badge, and the avatar
   all display A's real details.
3. In devtools → Network, inspect the `POST /api/chat` request body:
   confirm `userId` is A's actual UUID, not `"user-lina"`.
4. Start a Reading exam as A, answer a few questions, submit; confirm a 200
   response, not a 403.
5. Log out, log in as B, repeat step 2; confirm every identity surface
   changed to B's details without a manual page reload.

## Dependencies

None blocking — this can be implemented independently. However,
[03 — Opportunity Matching Seed Data](03-opportunity-matching-seed.md)
depends on this task for full end-to-end verification, since its seed is
keyed to the real user UUID this task starts sending.

## Estimated Effort

1 hour.

## Risk

**Medium.** This touches the chat request payload and the exam
session-creation path — both are demo-critical surfaces. Mitigation: keep
`CURRENT_USER_ID` exported as an explicit fallback (never delete it) so a
failed or slow profile fetch degrades to today's known behavior instead of
sending `undefined` or crashing. Do not attempt to also fix speaking
history's server-side user scoping in the same change — keep this task's
surface area to the frontend identity wiring only.

## Status

Completed. `chat-shell.tsx`, `app/exam/page.tsx`,
`app/speaking/history/page.tsx`, `components/ui/sidebar.tsx` and
`lib/current-user.ts` all updated per plan. `chat-input.tsx` also required
a small addition (a `disabled` prop gating Send/Speaking/Writing) — not in
the document's file list, but necessary to satisfy this same document's
own explicit acceptance criterion ("Send, mic, and pen controls are
disabled until the profile resolves"), since that's the only file
containing those controls' disabled state. Verified live with a real
headless-browser (Playwright/Chromium) session against two freshly
registered accounts through the real Gateway/user-service auth flow: chat
header, sidebar badge and the `POST /api/chat` body all reflect the real
account's UUID/email (not `"user-lina"`/`"Lina Ahmadi"`); the Send button
is disabled while the profile is loading and enables once it resolves;
switching accounts (cookie swap + navigation) updates every identity
surface; and an exam session created under the real account submits with
`200`, not `403`, verified through the real Gateway `examOwnership`
middleware (not just the internal API key path used in an earlier task).

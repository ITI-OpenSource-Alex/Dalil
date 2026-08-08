# GOA-062 — Exam Progress Tab Design

**Ticket:** GOA-062 (Frontend, P2, 2 SP)  
**Dependencies:** GOA-029 (profile page), GOA-060 (exam history/progress APIs)  
**Date:** 2026-08-08  
**Status:** Approved for implementation planning (revised after review)

## Goal

Add an **Exam Progress** tab on `/profile` alongside **Opportunities**, showing per-skill band trends (Chart.js), weak-area callouts, recent exams with View Results links, an estimated overall IELTS band, and an empty state CTA when the user has no exam history.

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Profile layout | Keep header / account / application form / CV above. Replace bottom Opportunities section with tabs: **Opportunities** \| **Exam Progress**. Default tab: Opportunities. |
| Chart presentation | One Chart.js line chart with a pill skill selector (Reading / Listening / Speaking / Writing). |
| Component ownership | Profile-local module under `components/profile/exam-progress/` (Approach 1). Do not abstract for dashboard reuse in this ticket. |
| View Results | Add `sessionId` to exam history API items so links go to `/exam/results?session=…&skill=…`. |
| Result ownership (IDOR) | Closing `GET …/result` without owner check is in scope for this ticket (see Security). |
| Empty illustration | Use existing `EmptyState` + Lucide icon; CTA copy and `/exam` link satisfy AC/E2E. Custom SVG is optional polish, not required. |
| Band rounding | Average latest band per skill that has data, then `roundToBand()` from `lib/ielts.ts` (nearest half-band; `.25` rounds up). Partial skills allowed (unlike onboarding `computeOverallBand`). |
| Multi-fetch failures | Per-resource status — soft-fail weak-areas; hard-fail tab only if progress **and** history both fail, or any returns upgrade-required (see Error model). |
| E2E strategy | **Hybrid (C):** mocked routes for empty/UI/chronology; one live smoke when exam stack is up, otherwise skip with documented gate. |

## Architecture

```
/profile (page.tsx)
  ├─ header, account, ProfileForm, CvUploadPanel  (unchanged)
  └─ Tabs (underline)
       ├─ Opportunities → OpportunityMatchesSection (moved from bottom section)
       └─ Exam Progress → ExamProgressTab
            ├─ useExamProgressTab()  → parallel GET progress + history + weak-areas
            ├─ EmptyState | upgrade | hard-error | content (+ optional soft errors)
            ├─ EstimatedOverallBand
            ├─ SkillTrendChart (skill pills + Line chart)
            ├─ WeakAreasPanel
            └─ RecentExamsList
```

### Data sources (browser → gateway)

All three are paid-tier (`RequirePaid`). Reuse `SubscriptionRequiredError` / upgrade UX from `useExamProgress`.

| Need | Client function | Gateway | Exam service |
|------|-----------------|---------|--------------|
| Trend points | `getExamProgress()` (exists) | `GET /api/exam/progress` | `GET /users/:id/progress` |
| Weak areas | `getWeakAreas()` (new) | `GET /api/exam/weak-areas` | `GET /users/:id/weak-areas` |
| Recent exams | `getExamHistory(page=1)` (new) | `GET /api/exam/history?page=1` | `GET /users/:id/exam-history` |
| Overall band | Client-derived via `roundToBand` | — | Average of **latest** progress point per skill that has data |
| View Results | Uses `sessionId` on history item | `GET /api/exam/sessions/:id/result` (owner-checked) | Must verify session belongs to JWT user |

Frontend never calls exam-service URLs with `:id` directly; the gateway injects the authenticated user for history/progress/weak-areas.

## Security — View Results IDOR (in scope)

**Gap today:** Gateway `GetResult` only requires a logged-in user, then proxies `GET /sessions/{id}/result`. Exam `SessionService.get_result` loads by `session_id` and does **not** compare `session["user_id"]` to the caller. History is already user-scoped (list won’t leak others’ IDs), but a guessed UUID still works — adding `sessionId` to history makes this path more important to close.

**Required fix (this ticket):**

1. Gateway `GetResult`: pass authenticated JWT `user_id` to the exam service (query header or query param consistent with other session routes such as listening submit / heartbeat).
2. Exam `get_result`: if `session["user_id"] !=` caller → `403`. Same ownership check for writing result path used by that endpoint.
3. Test: owner can fetch; non-owner receives 403.

**Known limitation (document, out of GOA-062 product fix):** Reading and Listening `/exam/results` currently hydrate from **sessionStorage** only (no server GET breakdown). View Results from profile still links correctly; after a new browser/session the R/L detail page may show “No result found” for the owner. Restoring server-backed R/L results is a follow-up, not this ticket. Writing/Speaking use the API and benefit from the ownership fix immediately.

## Backend change (in scope)

### A. `sessionId` on history

1. Add `session_id: UUID` with alias `sessionId` to `ExamHistoryItem` in `services/exam/app/schemas/history.py`.
2. Select `r.session_id` in `ExamHistoryRepository.get_history_page`.
3. Pass `session_id=row["session_id"]` when constructing `ExamHistoryItem` in `HistoryService.get_history`.
4. Coverage: history item serializes `sessionId`.
5. Gateway history proxy already forwards JSON — no shape change beyond the new field.

### B. Result ownership

As in Security section above (`get_result` + gateway `GetResult`).

## Frontend components

Path: `services/frontend/components/profile/exam-progress/`

| Component | Role |
|-----------|------|
| `ExamProgressTab` | Loads data via hook; branches empty / upgrade / hard-error / content. |
| `EstimatedOverallBand` | Partial-skill average → `roundToBand`; disclaimer “based on practice exams”. |
| `SkillTrendChart` | Pill skill selector + Chart.js `<Line />`. Last ≤10 points, chronological left→right, Y-axis 0–9. Pattern adapted from `components/speaking/band-trend-chart.tsx` (no forced shared abstraction). |
| `WeakAreasPanel` | One card per skill that has a weak-area string; label + **Practise Now** → `/exam`. Soft-error slot if weak-areas fetch failed. |
| `RecentExamsList` | First 5 history items: skill icon, Academic/General badge, band, date, **View Results** → `/exam/results?session=…&skill=…`. |

### Profile page change

`services/frontend/app/(app)/profile/page.tsx`:

- Remove standalone bottom `OpportunityMatchesSection` mount.
- Wrap Opportunities + Exam Progress in `Tabs` / `TabsList` / `TabsTrigger` / `TabsPanel` from `components/ui/tabs.tsx` (`variant="underline"`).
- Default value: `opportunities`.

### API / hooks

- Extend `services/frontend/lib/exam-api.ts` with:
  - `ExamHistoryItem` type including `sessionId: string`
  - `getExamHistory(page?: number)`
  - `getWeakAreas(): Promise<Partial<Record<skill, string>>>`
- Add `useExamProgressTab` that fetches the three endpoints in parallel and exposes **per-resource** results (not a single conflated success blob).

### Error model (three fetches, one tab)

Each of `progress`, `history`, `weakAreas` tracks its own outcome: `loading | success | error | upgrade-required`.

| Condition | UI |
|-----------|-----|
| Any resource `upgrade-required` | Whole tab shows upgrade CTA (paid-tier). |
| `progress` and `history` both `error` | Hard error: `Alert` + Retry for the tab. |
| `progress` success-empty **and** `history` success-empty | Full empty state + “Start your first practice exam” → `/exam`. |
| `progress` and/or `history` success with data | Render content from whatever succeeded. |
| `weakAreas` `error` while content shows | Soft fail: inline message on Weak Areas section; charts/list still render. Retry may re-fetch all three. |
| `progress` error, `history` success (or vice versa) | Render the successful resource; inline `Alert` for the failed one (not full-tab hard error). |

**Empty** = both progress and history succeeded and contain no exam data (history length 0; every skill’s progress array missing/empty). Weak-areas empty object does not by itself trigger empty state.

### Overall band rules

1. For each of reading/listening/speaking/writing, if progress has ≥1 point, take the **last** point’s `band` (API returns chronological order per GOA-060).
2. If no skills have data, omit the estimate block (empty state covers this).
3. Mean of available latest bands → `roundToBand(mean)` from `services/frontend/lib/ielts.ts`.  
   Explicit tie rule (already implemented there): nearest half-band; a mean ending in `.25` rounds **up** to the next half-band (e.g. 6.25 → 6.5), `.75` up to the next whole (6.75 → 7.0). Uses `Math.round(mean * 2) / 2`.
4. Unlike `computeOverallBand`, **do not** require all four skills — practice estimate is honest about partial coverage; disclaimer remains.
5. Disclaimer text exactly: `based on practice exams` (visible near the estimate).
6. Display with `formatBand` (one decimal).

### Empty / paid / loading

- **Empty:** `EmptyState` with CTA button text `Start your first practice exam` linking to `/exam`.
- **Upgrade-required:** Same pattern as dashboard / `useExamProgress` (upgrade CTA, not fake data).
- **Skill with no points:** Chart area shows “No exams for this skill yet”; do not swap the whole tab to empty if other skills have data.
- **Weak areas `{}`:** Hide cards; do not invent placeholders.
- **Loading:** Skeletons inside the Exam Progress panel only.

## Testing / definition of done

### Backend

- History item includes `sessionId` in API JSON.
- Non-owner `GET` result → 403; owner → 200 (or existing success shape).

### Frontend E2E — hybrid (C)

File: `services/frontend/test/e2e/exam-progress.spec.ts` (plus optional live file/suite gated by env).

**Always run (mocked `page.route` against gateway):**

1. No exam history → empty state; CTA text and `/exam` href correct.
2. Mocked one Reading point → open Exam Progress tab; score visible in chart and/or recent list.
3. Mocked two Reading points (6.0 then 7.0) → both points in correct chronological order.
4. Soft-fail smoke (optional but recommended): weak-areas 500 + progress/history OK → charts still show; weak-areas inline error.

**Live smoke (ticket DoD wording):**

- Complete one exam (reuse reading/exam-flow helpers against real gateway+exam when available), open `/profile` → Exam Progress, assert score appears in trend chart.
- Complete two Reading exams with bands 6.0 and 7.0 (or seed equivalent via real API), assert both chronological points.

**Gate:** Live cases run only when an explicit env flag is set (e.g. `E2E_LIVE_EXAM=1`) **and** required services are reachable; otherwise `test.skip` with a one-line reason in the report. CI default = mocked suite only. Document the flag in the plan/README note for local/demo runs that want literal DoD coverage.

This does **not** silently redefine DoD as mocks-only: mocks cover UI/empty/chronology in every CI; live smoke is the path that also exercises `sessionId` end-to-end through gateway when the stack is up.

## Out of scope

- GOA-061 orchestration personalisation
- Dashboard reuse of these components
- Profile edit backend / autosave changes (already GOA-029)
- Custom empty-state SVG asset (optional later)
- Changing Opportunities matching behaviour
- Server-backed Reading/Listening results hydration for `/exam/results` (known limitation; follow-up)

## File touch list (expected)

**Create**

- `docs/superpowers/specs/2026-08-08-goa-062-exam-progress-tab-design.md` (this file)
- `services/frontend/components/profile/exam-progress/*`
- `services/frontend/app/hooks/useExamProgressTab.ts` (or under profile folder)
- `services/frontend/test/e2e/exam-progress.spec.ts` (mocked + gated live)

**Modify**

- `services/exam/app/schemas/history.py`
- `services/exam/app/repositories/history_repository.py`
- `services/exam/app/services/history_service.py`
- `services/exam/app/services/session_service.py` (owner check on `get_result`)
- `services/exam/app/api/sessions.py` (pass caller user id into service)
- Exam tests under `services/exam/tests/`
- `services/gateway/handlers/exam.go` (`GetResult` forwards authenticated user)
- Gateway exam handler tests
- `services/frontend/lib/exam-api.ts`
- `services/frontend/app/(app)/profile/page.tsx`
- Possibly `services/frontend/test/e2e/profile.spec.ts` if shared helpers needed

## Spec self-review

- [x] No TBD/TODO placeholders for locked decisions
- [x] Layout, chart mode, View Results, IDOR, rounding, partial-fetch, and E2E hybrid are explicit
- [x] Scope: FE tab + history `sessionId` + result ownership check; R/L sessionStorage gap documented out of scope
- [x] AC mapped: tabs, Chart.js trends, weak areas + Practise Now, recent 5 + View Results, empty CTA, estimated band + disclaimer
- [x] DoD testing approach explicitly hybrid — not mocks silently replacing live wording

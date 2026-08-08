# GOA-062 — Exam Progress Tab Design

**Ticket:** GOA-062 (Frontend, P2, 2 SP)  
**Dependencies:** GOA-029 (profile page), GOA-060 (exam history/progress APIs)  
**Date:** 2026-08-08  
**Status:** Approved for implementation planning

## Goal

Add an **Exam Progress** tab on `/profile` alongside **Opportunities**, showing per-skill band trends (Chart.js), weak-area callouts, recent exams with View Results links, an estimated overall IELTS band, and an empty state CTA when the user has no exam history.

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Profile layout | Keep header / account / application form / CV above. Replace bottom Opportunities section with tabs: **Opportunities** \| **Exam Progress**. Default tab: Opportunities. |
| Chart presentation | One Chart.js line chart with a pill skill selector (Reading / Listening / Speaking / Writing). |
| Component ownership | Profile-local module under `components/profile/exam-progress/` (Approach 1). Do not abstract for dashboard reuse in this ticket. |
| View Results | Expand scope slightly: add `sessionId` to exam history API items so links go to `/exam/results?session=…&skill=…`. |
| Empty illustration | Use existing `EmptyState` + Lucide icon; CTA copy and `/exam` link satisfy AC/E2E. Custom SVG is optional polish, not required. |

## Architecture

```
/profile (page.tsx)
  ├─ header, account, ProfileForm, CvUploadPanel  (unchanged)
  └─ Tabs (underline)
       ├─ Opportunities → OpportunityMatchesSection (moved from bottom section)
       └─ Exam Progress → ExamProgressTab
            ├─ useExamProgressTab()  → parallel GET progress + history + weak-areas
            ├─ EmptyState | upgrade | error | content
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
| Overall band | Client-derived | — | Average of **latest** progress point per skill that has data |
| View Results | Uses `sessionId` on history item | — | Requires schema/repo change below |

Frontend never calls exam-service URLs with `:id` directly; the gateway injects the authenticated user.

## Backend change (in scope)

`ExamHistoryItem` today has no session id, but results UI requires `/exam/results?session=…`.

1. Add `session_id: UUID` with alias `sessionId` to `ExamHistoryItem` in `services/exam/app/schemas/history.py`.
2. Select `r.session_id` in `ExamHistoryRepository.get_history_page` (join already uses `exam_sessions`; `r.session_id` is on `exam_results`).
3. Pass `session_id=row["session_id"]` when constructing `ExamHistoryItem` in `HistoryService.get_history`.
4. Add/adjust unit or integration coverage so a history item serializes `sessionId`.
5. Gateway JSON proxy needs no structural change beyond forwarding the new field.

## Frontend components

Path: `services/frontend/components/profile/exam-progress/`

| Component | Role |
|-----------|------|
| `ExamProgressTab` | Loads data via hook; branches empty / upgrade / error / content. |
| `EstimatedOverallBand` | Average of latest band per skill with data; round to nearest 0.5; always show disclaimer “based on practice exams”. |
| `SkillTrendChart` | Pill skill selector + Chart.js `<Line />`. Last ≤10 points, chronological left→right, Y-axis 0–9. Pattern adapted from `components/speaking/band-trend-chart.tsx` (do not force a shared abstraction). |
| `WeakAreasPanel` | One card per skill that has a weak-area string; label + **Practise Now** → `/exam`. |
| `RecentExamsList` | First 5 history items: skill icon, Academic/General badge, band, date, **View Results** link. |

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
- Add `useExamProgressTab` (or equivalent) that fetches the three endpoints in parallel and normalizes status: `idle | loading | success | error | upgrade-required | empty`.
- **Empty** = success responses where history length is 0 and every skill’s progress array is missing/empty.

### Overall band rules

1. For each of reading/listening/speaking/writing, if progress has ≥1 point, take the **last** point’s `band` (API returns chronological order per GOA-060).
2. Average those values; if none, do not show the estimate block (empty state covers this).
3. Round to nearest 0.5 (IELTS half-band convention).
4. Disclaimer text exactly: `based on practice exams` (visible near the estimate).

### Empty / error / paid states

- **Empty:** `EmptyState` with CTA button text `Start your first practice exam` linking to `/exam`.
- **Upgrade-required:** Same pattern as dashboard / `useExamProgress` (upgrade CTA, not fake data).
- **Error:** Inline `Alert` + Retry inside the Exam Progress panel only.
- **Skill with no points:** Chart area shows a short “No exams for this skill yet” message; do not swap the whole tab to empty if other skills have data.
- **Weak areas `{}`:** Hide panel or show nothing; do not invent placeholders.
- **Loading:** Skeletons inside the Exam Progress panel only.

## Testing / definition of done

### Backend

- History item includes `sessionId` in API JSON (unit or integration).

### Frontend E2E (Playwright)

Prefer `services/frontend/test/e2e/exam-progress.spec.ts` using auth fixtures + `page.route` mocks for:

- `GET /api/exam/progress`
- `GET /api/exam/history`
- `GET /api/exam/weak-areas`

Cases:

1. No exam history → empty state visible; CTA text and `/exam` href correct.
2. One completed exam (mocked progress + history) → navigate to Exam Progress tab; score appears in trend chart / list.
3. Two Reading exams bands 6.0 and 7.0 → both data points in correct chronological order (earlier date left / lower index chronologically).
4. Visual smoke: empty state before any exams (covered by case 1).

Full live “complete one exam then assert chart” can reuse exam-flow helpers if environment allows; mocked routes satisfy the ticket’s E2E intent when gateway is stubbed in CI.

## Out of scope

- GOA-061 orchestration personalisation
- Dashboard reuse of these components
- Profile edit backend / autosave changes (already GOA-029)
- Custom empty-state SVG asset (optional later)
- Changing Opportunities matching behaviour

## File touch list (expected)

**Create**

- `docs/superpowers/specs/2026-08-08-goa-062-exam-progress-tab-design.md` (this file)
- `services/frontend/components/profile/exam-progress/*`
- `services/frontend/app/hooks/useExamProgressTab.ts` (or under profile folder)
- `services/frontend/test/e2e/exam-progress.spec.ts`

**Modify**

- `services/exam/app/schemas/history.py`
- `services/exam/app/repositories/history_repository.py`
- `services/exam/app/services/history_service.py`
- Exam history tests under `services/exam/tests/`
- `services/frontend/lib/exam-api.ts`
- `services/frontend/app/(app)/profile/page.tsx`
- Possibly `services/frontend/test/e2e/profile.spec.ts` if shared helpers needed

## Spec self-review

- [x] No TBD/TODO placeholders
- [x] Layout, chart mode, View Results, and empty-state decisions are explicit
- [x] Scope is one feature (FE tab + minimal history `sessionId` fix)
- [x] AC mapped: tabs, Chart.js trends, weak areas + Practise Now, recent 5 + View Results, empty CTA, estimated band + disclaimer

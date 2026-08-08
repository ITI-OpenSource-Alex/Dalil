# GOA-062 Exam Progress Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Exam Progress tab on `/profile` (alongside Opportunities) with skill trend charts, weak areas, recent exams + View Results, estimated overall band, empty state, plus history `sessionId` and result-owner IDOR fix.

**Architecture:** Profile keeps form/CV above; underline Tabs host Opportunities | Exam Progress. Tab data comes from three parallel gateway GETs (`/api/exam/progress`, `/history`, `/weak-areas`) with per-resource error handling. Chart.js line chart with skill pills. Small exam-service + gateway changes for `sessionId` on history and `X-User-Id` ownership on `GET …/result`.

**Tech Stack:** Next.js/React/TypeScript frontend, Chart.js + react-chartjs-2, Radix Tabs, Playwright; FastAPI exam service; Go Fiber gateway.

**Spec:** `docs/superpowers/specs/2026-08-08-goa-062-exam-progress-tab-design.md`

## Global Constraints

- Frontend lives under `services/frontend/` (path alias `@/`).
- Browser calls gateway only (`NEXT_PUBLIC_API_URL` + `/api/exam/...`), never exam-service `:id` URLs.
- Progress/history/weak-areas are paid-tier; reuse `SubscriptionRequiredError` / upgrade UX.
- Estimated band: average of latest progress point per skill that has data → `roundToBand()` from `lib/ielts.ts` (`.25` up); partial skills allowed; disclaimer text exactly `based on practice exams`.
- Empty CTA text exactly `Start your first practice exam` → `/exam`.
- View Results → `/exam/results?session={sessionId}&skill={Skill}` (Pascal Case skill for existing results page).
- Reading/Listening sessionStorage results gap is out of scope; still emit the link.
- E2E hybrid: mocked always; live smoke only when `E2E_LIVE_EXAM=1`.
- Do not refactor unrelated profile/CV code. Do not abstract charts for dashboard reuse.

## File map

| Path | Responsibility |
|------|----------------|
| `services/exam/app/schemas/history.py` | Add `sessionId` on `ExamHistoryItem` |
| `services/exam/app/repositories/history_repository.py` | SELECT `r.session_id` |
| `services/exam/app/services/history_service.py` | Map `session_id` into items |
| `services/exam/app/api/sessions.py` | Require `X-User-Id` on GET result |
| `services/exam/app/services/session_service.py` | Owner check in `get_result` |
| `services/exam/tests/test_exam_history.py` | History `sessionId` assertions |
| `services/exam/tests/test_get_result_ownership.py` | New owner/non-owner tests |
| `services/gateway/handlers/exam.go` | `GetSessionResult` forwards `X-User-Id` |
| `services/gateway/handlers/exam_test.go` | Assert header forwarded |
| `services/frontend/lib/exam-api.ts` | `getExamHistory`, `getWeakAreas`, types |
| `services/frontend/lib/exam-progress.ts` | `estimateOverallPracticeBand`, empty helpers |
| `services/frontend/test/unit/exam-progress.test.ts` | Unit tests for estimate/empty |
| `services/frontend/app/hooks/useExamProgressTab.ts` | Parallel fetch + per-resource status |
| `services/frontend/components/profile/exam-progress/*` | Tab UI pieces |
| `services/frontend/app/(app)/profile/page.tsx` | Tabs wiring |
| `services/frontend/test/e2e/exam-progress.spec.ts` | Mocked E2E |
| `services/frontend/test/e2e/exam-progress-live.spec.ts` | Gated live smoke |

---

### Task 1: History API — add `sessionId`

**Files:**
- Modify: `services/exam/app/schemas/history.py`
- Modify: `services/exam/app/repositories/history_repository.py`
- Modify: `services/exam/app/services/history_service.py`
- Modify: `services/exam/tests/test_exam_history.py`

**Interfaces:**
- Produces: `ExamHistoryItem` JSON includes `sessionId` (UUID string). CamelCase via existing alias pattern.

- [ ] **Step 1: Extend `_make_row` and add a failing history assertion**

In `services/exam/tests/test_exam_history.py`, update `_make_row` to include `session_id`:

```python
def _make_row(
    *,
    user_id: UUID,
    skill: str,
    band: float,
    graded_at: datetime,
    exam_type: str = "academic",
    duration_seconds: int = 3600,
    section_scores: dict[str, Any] | None = None,
    agent_responses: dict[str, Any] | None = None,
    session_id: UUID | None = None,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "session_id": session_id or uuid4(),
        "skill_area": skill,
        "exam_type": exam_type,
        "band_score": band,
        "graded_at": graded_at,
        "duration_seconds": duration_seconds,
        "section_scores": section_scores or {},
        "agent_responses": agent_responses,
    }
```

Add (or extend an existing history list test):

```python
@pytest.mark.asyncio
async def test_history_includes_session_id():
    user_id = uuid4()
    session_id = uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _make_row(
            user_id=user_id,
            skill="reading",
            band=6.5,
            graded_at=base,
            session_id=session_id,
        )
    ]

    async with _build_client(rows) as client:
        resp = await client.get(f"/users/{user_id}/exam-history")

    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["sessionId"] == str(session_id)
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd "services/exam"
python -m pytest tests/test_exam_history.py::test_history_includes_session_id -v
```

Expected: FAIL (missing field / validation / KeyError on `session_id`).

- [ ] **Step 3: Implement schema + repo + service**

`services/exam/app/schemas/history.py` — add field:

```python
from uuid import UUID
# ...
class ExamHistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: UUID = Field(alias="sessionId")
    skill: str
    exam_type: str = Field(alias="examType")
    band_score: float = Field(alias="bandScore")
    date: datetime
    duration: Optional[int] = None
    feedback_summary: Optional[str] = None
```

`history_repository.py` — add `r.session_id` to the SELECT list in `get_history_page`.

`history_service.py` — pass through:

```python
ExamHistoryItem(
    session_id=row["session_id"],
    skill=row["skill_area"],
    exam_type=row["exam_type"],
    band_score=float(row["band_score"]),
    date=row["graded_at"],
    duration=row.get("duration_seconds"),
    feedback_summary=extract_feedback_summary(row.get("agent_responses")),
)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd "services/exam"
python -m pytest tests/test_exam_history.py -v
```

Expected: PASS (including new test; fix any fixtures that construct `ExamHistoryItem` without `session_id`).

- [ ] **Step 5: Commit**

```bash
git add services/exam/app/schemas/history.py \
  services/exam/app/repositories/history_repository.py \
  services/exam/app/services/history_service.py \
  services/exam/tests/test_exam_history.py
git commit -m "feat(exam): include sessionId on exam history items"
```

---

### Task 2: Close IDOR on GET session result

**Files:**
- Modify: `services/exam/app/api/sessions.py`
- Modify: `services/exam/app/services/session_service.py`
- Create: `services/exam/tests/test_get_result_ownership.py`
- Modify: `services/gateway/handlers/exam.go`
- Modify: `services/gateway/handlers/exam_test.go`

**Interfaces:**
- Consumes: heartbeat pattern — `X-User-Id` header from gateway JWT.
- Produces: owner → existing 200 body; non-owner → 403 `"Session belongs to another user"`.

- [ ] **Step 1: Write failing ownership tests (exam service)**

Create `services/exam/tests/test_get_result_ownership.py` mirroring patterns from `test_api_integration.py` / heartbeat ownership: fake session repo with owner A, call GET result with `X-User-Id: B` → 403; with A → 200.

Minimal shape (adapt imports to project fakes if a shared fake exists; otherwise inline):

```python
"""Owner check on GET /sessions/{id}/result."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Wire the real sessions router with dependency overrides for SessionService
# OR call SessionService.get_result directly with a fake repo.
# Prefer service-level unit test if router wiring is heavy:

from fastapi import HTTPException
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_get_result_rejects_non_owner(monkeypatch):
    owner_id = uuid4()
    other_id = uuid4()
    session_id = uuid4()

    class FakeSessions:
        async def get_by_id(self, sid):
            return {
                "id": session_id,
                "user_id": owner_id,
                "status": "scored",
                "skill_area": "speaking",
                "question_id": uuid4(),
            }

    class FakeResults:
        async def get_by_session(self, sid):
            return {
                "id": uuid4(),
                "session_id": session_id,
                "user_id": owner_id,
                "skill_area": "speaking",
                "raw_score": None,
                "band_score": 6.5,
                "section_scores": "{}",
                "graded_at": datetime.now(timezone.utc),
            }

    class FakeQuestions:
        async def get_by_id(self, qid):
            return {"id": qid, "answer_key": "{}"}

    svc = SessionService(
        session_repository=FakeSessions(),
        question_repository=FakeQuestions(),
        result_repository=FakeResults(),
        writing_response_repository=None,  # adjust to match real ctor defaults
        writing_client=None,
    )
    # If ctor requires all deps, pass lightweight stubs matching __init__.

    with pytest.raises(HTTPException) as exc:
        await svc.get_result(session_id, requester_id=other_id)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_result_allows_owner():
    # Same fakes; requester_id == owner_id; assert band_score == 6.5
    ...
```

Adjust constructor args to match `SessionService.__init__` exactly (read the file; stub unused writing deps).

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd "services/exam"
python -m pytest tests/test_get_result_ownership.py -v
```

Expected: FAIL (`get_result` missing `requester_id` or no 403).

- [ ] **Step 3: Implement owner check**

`session_service.py` — change signature and check after load (same message as listening submit):

```python
async def get_result(self, session_id: UUID, requester_id: UUID) -> dict[str, Any]:
    session = await self.session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if str(session["user_id"]) != str(requester_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session belongs to another user",
        )
    # ... existing status / skill branching unchanged
```

`sessions.py`:

```python
from fastapi import Header

@router.get("/{session_id}/result")
async def get_result(
    session_id: UUID,
    x_user_id: UUID = Header(),
    service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    return await service.get_result(session_id, requester_id=x_user_id)
```

Update any other callers of `get_result` in tests to pass `requester_id`.

- [ ] **Step 4: Gateway forwards `X-User-Id`**

In `services/gateway/handlers/exam.go`, change `GetSessionResult` to match `Heartbeat`:

```go
func (h *ExamHandler) GetSessionResult(c *fiber.Ctx) error {
	userID, err := authenticatedUserID(c)
	if err != nil {
		return err
	}
	target, err := h.sessionURL(c.Params("sessionId"), "result")
	if err != nil {
		return err
	}
	return h.forwardWith(c, http.MethodGet, target, nil, map[string]string{
		"X-User-Id": userID,
	})
}
```

Add a test in `exam_test.go` (mirror heartbeat/listening ownership tests): upstream receives `X-User-Id` equal to JWT user.

- [ ] **Step 5: Run exam + gateway tests**

```bash
cd "services/exam"
python -m pytest tests/test_get_result_ownership.py tests/test_api_integration.py -v

cd "../gateway"
go test ./handlers/ -run Exam -count=1
```

Expected: PASS (fix any broken callers of `get_result`).

- [ ] **Step 6: Commit**

```bash
git add services/exam/app/api/sessions.py \
  services/exam/app/services/session_service.py \
  services/exam/tests/test_get_result_ownership.py \
  services/exam/tests \
  services/gateway/handlers/exam.go \
  services/gateway/handlers/exam_test.go
git commit -m "fix(exam): require session owner on GET result"
```

---

### Task 3: Frontend API clients for history + weak-areas

**Files:**
- Modify: `services/frontend/lib/exam-api.ts`
- Test: manual typecheck / existing vitest if any api tests exist

**Interfaces:**
- Consumes: gateway `GET /api/exam/history?page=`, `GET /api/exam/weak-areas`
- Produces:
  - `ExamHistoryItem { sessionId, skill, examType, bandScore, date, duration?, feedbackSummary? }`
  - `getExamHistory(page?: number): Promise<ExamHistoryItem[]>`
  - `WeakAreas = Partial<Record<"reading"|"listening"|"speaking"|"writing", string>>`
  - `getWeakAreas(): Promise<WeakAreas>`

- [ ] **Step 1: Add types + functions next to `getExamProgress`**

In `services/frontend/lib/exam-api.ts`:

```typescript
export type ExamSkillKey = "reading" | "listening" | "speaking" | "writing";

export type ExamHistoryItem = {
  sessionId: string;
  skill: string;
  examType: string;
  bandScore: number;
  date: string;
  duration?: number | null;
  feedbackSummary?: string | null;
};

export type WeakAreas = Partial<Record<ExamSkillKey, string>>;

export async function getExamHistory(page = 1): Promise<ExamHistoryItem[]> {
  return dedupe(`GET ${API_BASE}/history?page=${page}`, async () => {
    const response = await fetch(`${API_BASE}/history?page=${page}`, {
      ...fetchOptions,
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      await throwForResponse(response, "exam");
    }
    return response.json();
  });
}

export async function getWeakAreas(): Promise<WeakAreas> {
  return dedupe(`GET ${API_BASE}/weak-areas`, async () => {
    const response = await fetch(`${API_BASE}/weak-areas`, {
      ...fetchOptions,
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      await throwForResponse(response, "exam");
    }
    return response.json();
  });
}
```

Keep field names matching gateway JSON aliases (`sessionId`, `examType`, `bandScore`, `feedbackSummary`). If the gateway returns snake_case for any field, normalize in the client — verify with a quick network inspection or exam OpenAPI; prefer trusting Pydantic `by_alias` serialization (camelCase).

- [ ] **Step 2: Typecheck**

```bash
cd "services/frontend"
npx tsc --noEmit -p tsconfig.json 2>&1 | head -n 40
```

Expected: no new errors in `exam-api.ts`.

- [ ] **Step 3: Commit**

```bash
git add services/frontend/lib/exam-api.ts
git commit -m "feat(frontend): add exam history and weak-areas API clients"
```

---

### Task 4: Practice overall-band helper (unit-tested)

**Files:**
- Create: `services/frontend/lib/exam-progress.ts`
- Create: `services/frontend/test/unit/exam-progress.test.ts`

**Interfaces:**
- Consumes: `ExamProgress` from `exam-api`, `roundToBand` / `formatBand` from `ielts.ts`
- Produces:
  - `estimateOverallPracticeBand(progress: ExamProgress): number | null`
  - `isExamProgressEmpty(progress, historyLength): boolean`

- [ ] **Step 1: Write failing unit tests**

```typescript
import { describe, expect, it } from "vitest";
import {
  estimateOverallPracticeBand,
  isExamProgressEmpty,
} from "@/lib/exam-progress";

describe("estimateOverallPracticeBand", () => {
  it("returns null when no skills have points", () => {
    expect(estimateOverallPracticeBand({})).toBeNull();
  });

  it("averages latest bands and rounds with IELTS .25-up rule", () => {
    // latest reading 6.0, latest listening 6.5 → mean 6.25 → 6.5
    expect(
      estimateOverallPracticeBand({
        reading: [
          { date: "2026-01-01", band: 5.5 },
          { date: "2026-02-01", band: 6.0 },
        ],
        listening: [{ date: "2026-02-01", band: 6.5 }],
      }),
    ).toBe(6.5);
  });

  it("uses only skills that have data (partial OK)", () => {
    expect(
      estimateOverallPracticeBand({
        reading: [{ date: "2026-01-01", band: 7.0 }],
      }),
    ).toBe(7.0);
  });
});

describe("isExamProgressEmpty", () => {
  it("is true when history empty and no progress points", () => {
    expect(isExamProgressEmpty({}, 0)).toBe(true);
  });

  it("is false when history has rows", () => {
    expect(isExamProgressEmpty({}, 1)).toBe(false);
  });
});
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd "services/frontend"
npx vitest run test/unit/exam-progress.test.ts
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```typescript
import type { ExamProgress } from "@/lib/exam-api";
import { roundToBand } from "@/lib/ielts";

const SKILLS = ["reading", "listening", "speaking", "writing"] as const;

export function estimateOverallPracticeBand(
  progress: ExamProgress,
): number | null {
  const latest: number[] = [];
  for (const skill of SKILLS) {
    const points = progress[skill];
    if (!points || points.length === 0) continue;
    latest.push(points[points.length - 1].band);
  }
  if (latest.length === 0) return null;
  const mean = latest.reduce((a, b) => a + b, 0) / latest.length;
  return roundToBand(mean);
}

export function isExamProgressEmpty(
  progress: ExamProgress,
  historyLength: number,
): boolean {
  if (historyLength > 0) return false;
  return SKILLS.every((skill) => !progress[skill]?.length);
}
```

- [ ] **Step 4: Run — expect PASS**

```bash
npx vitest run test/unit/exam-progress.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add services/frontend/lib/exam-progress.ts \
  services/frontend/test/unit/exam-progress.test.ts
git commit -m "feat(frontend): add practice overall-band estimate helper"
```

---

### Task 5: `useExamProgressTab` hook (per-resource status)

**Files:**
- Create: `services/frontend/app/hooks/useExamProgressTab.ts`
- Optional unit test if the repo tests hooks; otherwise covered by E2E.

**Interfaces:**
- Consumes: `getExamProgress`, `getExamHistory`, `getWeakAreas`, `isSubscriptionRequiredError`
- Produces: see return type below

```typescript
export type ResourceStatus = "idle" | "loading" | "success" | "error" | "upgrade-required";

export type UseExamProgressTabResult = {
  progress: ExamProgress;
  history: ExamHistoryItem[];
  weakAreas: WeakAreas;
  progressStatus: ResourceStatus;
  historyStatus: ResourceStatus;
  weakAreasStatus: ResourceStatus;
  progressError: string | null;
  historyError: string | null;
  weakAreasError: string | null;
  /** Derived tab-level flags for the panel */
  tab: "loading" | "upgrade-required" | "empty" | "hard-error" | "content";
  retry: () => void;
};
```

Derived `tab` rules (from design):

1. If any resource is `upgrade-required` → `upgrade-required`
2. Else if still loading any of the three while none have failed hard yet and no success data yet → `loading` (or: loading until all three settle)
3. Else if progress **and** history both `error` → `hard-error`
4. Else if both success and `isExamProgressEmpty(progress, history.length)` → `empty`
5. Else → `content` (may include soft errors)

Settle all three with `Promise.allSettled` so one failure does not abort others.

- [ ] **Step 1: Implement hook**

```typescript
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getExamHistory,
  getExamProgress,
  getWeakAreas,
  type ExamHistoryItem,
  type ExamProgress,
  type WeakAreas,
} from "@/lib/exam-api";
import { isExamProgressEmpty } from "@/lib/exam-progress";
import { isSubscriptionRequiredError } from "@/lib/subscription";

export type ResourceStatus =
  | "idle"
  | "loading"
  | "success"
  | "error"
  | "upgrade-required";

async function loadOne<T>(
  fn: () => Promise<T>,
): Promise<
  | { status: "success"; data: T }
  | { status: "error"; message: string }
  | { status: "upgrade-required" }
> {
  try {
    const data = await fn();
    return { status: "success", data };
  } catch (err) {
    if (isSubscriptionRequiredError(err)) {
      return { status: "upgrade-required" };
    }
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Request failed",
    };
  }
}

export function useExamProgressTab() {
  const [progress, setProgress] = useState<ExamProgress>({});
  const [history, setHistory] = useState<ExamHistoryItem[]>([]);
  const [weakAreas, setWeakAreas] = useState<WeakAreas>({});
  const [progressStatus, setProgressStatus] = useState<ResourceStatus>("idle");
  const [historyStatus, setHistoryStatus] = useState<ResourceStatus>("idle");
  const [weakAreasStatus, setWeakAreasStatus] =
    useState<ResourceStatus>("idle");
  const [progressError, setProgressError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [weakAreasError, setWeakAreasError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setProgressStatus("loading");
    setHistoryStatus("loading");
    setWeakAreasStatus("loading");
    setProgressError(null);
    setHistoryError(null);
    setWeakAreasError(null);

    const [p, h, w] = await Promise.all([
      loadOne(getExamProgress),
      loadOne(() => getExamHistory(1)),
      loadOne(getWeakAreas),
    ]);

    if (p.status === "success") {
      setProgress(p.data);
      setProgressStatus("success");
    } else if (p.status === "upgrade-required") {
      setProgressStatus("upgrade-required");
    } else {
      setProgressError(p.message);
      setProgressStatus("error");
    }

    if (h.status === "success") {
      setHistory(h.data);
      setHistoryStatus("success");
    } else if (h.status === "upgrade-required") {
      setHistoryStatus("upgrade-required");
    } else {
      setHistoryError(h.message);
      setHistoryStatus("error");
    }

    if (w.status === "success") {
      setWeakAreas(w.data);
      setWeakAreasStatus("success");
    } else if (w.status === "upgrade-required") {
      setWeakAreasStatus("upgrade-required");
    } else {
      setWeakAreasError(w.message);
      setWeakAreasStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const tab = useMemo(() => {
    const statuses = [progressStatus, historyStatus, weakAreasStatus];
    if (statuses.some((s) => s === "upgrade-required")) {
      return "upgrade-required" as const;
    }
    if (statuses.some((s) => s === "idle" || s === "loading")) {
      return "loading" as const;
    }
    if (progressStatus === "error" && historyStatus === "error") {
      return "hard-error" as const;
    }
    if (
      progressStatus === "success" &&
      historyStatus === "success" &&
      isExamProgressEmpty(progress, history.length)
    ) {
      return "empty" as const;
    }
    return "content" as const;
  }, [
    progressStatus,
    historyStatus,
    weakAreasStatus,
    progress,
    history.length,
  ]);

  return {
    progress,
    history,
    weakAreas,
    progressStatus,
    historyStatus,
    weakAreasStatus,
    progressError,
    historyError,
    weakAreasError,
    tab,
    retry: load,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add services/frontend/app/hooks/useExamProgressTab.ts
git commit -m "feat(frontend): add useExamProgressTab with per-resource status"
```

---

### Task 6: Exam Progress UI components

**Files:**
- Create: `services/frontend/components/profile/exam-progress/skill-trend-chart.tsx`
- Create: `services/frontend/components/profile/exam-progress/weak-areas-panel.tsx`
- Create: `services/frontend/components/profile/exam-progress/recent-exams-list.tsx`
- Create: `services/frontend/components/profile/exam-progress/estimated-overall-band.tsx`
- Create: `services/frontend/components/profile/exam-progress/exam-progress-tab.tsx`
- Create: `services/frontend/components/profile/exam-progress/index.ts`

**Interfaces:**
- Consumes: hook result, `estimateOverallPracticeBand`, UI primitives, Chart.js pattern from `components/speaking/band-trend-chart.tsx`
- Produces: `<ExamProgressTab />` ready for profile page

- [ ] **Step 1: `estimated-overall-band.tsx`**

```tsx
"use client";

import type { ExamProgress } from "@/lib/exam-api";
import { estimateOverallPracticeBand } from "@/lib/exam-progress";
import { formatBand } from "@/lib/ielts";
import { Heading, Text } from "@/components/ui";

export function EstimatedOverallBand({ progress }: { progress: ExamProgress }) {
  const band = estimateOverallPracticeBand(progress);
  if (band === null) return null;

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <Heading as="h3" size="xs" className="text-fg-muted">
        Estimated overall IELTS band
      </Heading>
      <p className="mt-1 text-3xl font-semibold text-fg">{formatBand(band)}</p>
      <Text size="sm" tone="muted" className="mt-1">
        based on practice exams
      </Text>
    </div>
  );
}
```

- [ ] **Step 2: `skill-trend-chart.tsx`**

Adapt speaking `BandTrendChart`: accept `{ date: string; band: number }[]`, pill `Tabs` or button group for skill keys, Y 0–9, last 10 chronological. Include `data-testid="skill-trend-chart"` and encode bands in an `sr-only` summary list for E2E (canvas is opaque to Playwright text).

```tsx
// Skill pills: reading|listening|speaking|writing
// When points.length === 0: Text "No exams for this skill yet"
// When points.length >= 1: Line chart (allow single point)
// data-testid={`trend-point-${index}`} on sr-only items with band text
```

Register Chart.js scales once (same as speaking chart). Resolve `--color-success` via `getComputedStyle`.

- [ ] **Step 3: `weak-areas-panel.tsx`**

```tsx
// Props: weakAreas, error: string | null, onRetry?: () => void
// If error: Alert soft fail
// Else map entries to cards: skill label + section string + Button "Practise Now" asChild Link /exam
// If no entries and no error: return null
```

Use British spelling **Practise Now** per ticket AC.

- [ ] **Step 4: `recent-exams-list.tsx`**

```tsx
// Props: items: ExamHistoryItem[] (caller passes slice(0,5))
// Row: skill icon (lucide BookOpen/Headphones/Mic/PenLine), Badge Academic|General,
//      formatBand(bandScore), formatted date, Link "View Results"
// href: `/exam/results?session=${sessionId}&skill=${toPascalSkill(skill)}`
```

```typescript
function toPascalSkill(skill: string): string {
  const s = skill.toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function examTypeLabel(examType: string): "Academic" | "General" {
  return examType.toLowerCase() === "general" ? "General" : "Academic";
}
```

- [ ] **Step 5: `exam-progress-tab.tsx` orchestrator**

Branch on `tab` from `useExamProgressTab()`:

- `loading` → skeletons
- `upgrade-required` → EmptyState / upgrade CTA like `IeltsSummaryWidget` (link `DEFAULT_UPGRADE_URL` or `/exam` consistent with dashboard)
- `empty` → EmptyState: title about no exams; actions Button “Start your first practice exam” → `/exam` (`data-testid="exam-progress-empty-cta"`)
- `hard-error` → Alert + Retry
- `content` → stack: EstimatedOverallBand, SkillTrendChart, WeakAreasPanel, RecentExamsList; plus inline Alerts if `progressError` xor `historyError`

Export from `index.ts`: `export { ExamProgressTab } from "./exam-progress-tab";`

- [ ] **Step 6: Smoke typecheck**

```bash
cd "services/frontend"
npx tsc --noEmit -p tsconfig.json 2>&1 | head -n 50
```

- [ ] **Step 7: Commit**

```bash
git add services/frontend/components/profile/exam-progress
git commit -m "feat(frontend): add Exam Progress tab UI components"
```

---

### Task 7: Wire Opportunities | Exam Progress tabs on profile

**Files:**
- Modify: `services/frontend/app/(app)/profile/page.tsx`

**Interfaces:**
- Consumes: `Tabs`, `TabsList`, `TabsTrigger`, `TabsPanel`, `OpportunityMatchesSection`, `ExamProgressTab`

- [ ] **Step 1: Replace bottom section with tabs**

Replace the standalone `{/* 5. Opportunity matches */}` block with:

```tsx
import { Tabs, TabsList, TabsTrigger, TabsPanel } from "@/components/ui";
import { ExamProgressTab } from "@/components/profile/exam-progress";

{/* 5. Opportunities | Exam Progress */}
<section className="space-y-4" aria-label="Profile tabs">
  <Tabs defaultValue="opportunities">
    <TabsList variant="underline">
      <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
      <TabsTrigger value="exam-progress">Exam Progress</TabsTrigger>
    </TabsList>
    <TabsPanel value="opportunities" className="pt-4">
      <OpportunityMatchesSection
        profileComplete={isProfileComplete(user.profile)}
        onFocusProfile={focusApplicationProfile}
      />
    </TabsPanel>
    <TabsPanel value="exam-progress" className="pt-4">
      <ExamProgressTab />
    </TabsPanel>
  </Tabs>
</section>
```

Ensure `Tabs` / triggers are re-exported from `@/components/ui` (they are via `components/ui/index.ts`). If not exported, import from `@/components/ui/tabs`.

Update the file header comment (no longer “five sections” only).

- [ ] **Step 2: Manual sanity (optional)** — `npm run dev`, open `/profile`, switch tabs.

- [ ] **Step 3: Commit**

```bash
git add services/frontend/app/\(app\)/profile/page.tsx
git commit -m "feat(frontend): add Exam Progress tab beside Opportunities on profile"
```

---

### Task 8: Mocked Playwright E2E (always-on CI)

**Files:**
- Create: `services/frontend/test/e2e/exam-progress.spec.ts`

**Interfaces:**
- Consumes: `./fixtures/auth`, `page.route` mocks for profile + three exam endpoints

- [ ] **Step 1: Write mocked specs**

```typescript
import { test, expect, Page } from "./fixtures/auth";

const GATEWAY = "http://localhost:8080";

function withCors(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Origin": "http://localhost:3000",
      "Access-Control-Allow-Credentials": "true",
    },
    body: JSON.stringify(body),
  };
}

const PROFILE = {
  id: "user-1",
  email: "amina.hassan@example.com",
  subscriptionTier: "pro",
  isVerified: true,
  profile: {
    userId: "user-1",
    degreeLevel: "Bachelors",
    gpa: 3.2,
    gpaScale: "4.0",
    ieltsScore: 7.0,
    ieltsListening: 7.0,
    ieltsReading: 7.0,
    ieltsWriting: 7.0,
    ieltsSpeaking: 7.0,
    targetCountries: ["Germany"],
    fieldOfStudy: "Computer Science",
    ects: 180,
    workExperienceYears: 1,
    extracurricularsScore: 5,
  },
};

async function mockProfile(page: Page) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(withCors(PROFILE)),
  );
}

async function openExamProgress(page: Page) {
  await page.goto("/profile");
  await page.getByRole("tab", { name: "Exam Progress" }).click();
}

test("empty state shows Start your first practice exam CTA", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(withCors({})),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(withCors([])),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({})),
  );

  await openExamProgress(page);

  const cta = page.getByTestId("exam-progress-empty-cta");
  await expect(cta).toHaveText("Start your first practice exam");
  await expect(cta).toHaveAttribute("href", "/exam");
});

test("one Reading score appears after opening Exam Progress", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({
        reading: [{ date: "2026-03-01T00:00:00Z", band: 6.5 }],
      }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(
      withCors([
        {
          sessionId: "11111111-1111-1111-1111-111111111111",
          skill: "reading",
          examType: "academic",
          bandScore: 6.5,
          date: "2026-03-01T00:00:00Z",
        },
      ]),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({ reading: "Section 3" })),
  );

  await openExamProgress(page);

  await expect(page.getByText("6.5").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "View Results" })).toHaveAttribute(
    "href",
    "/exam/results?session=11111111-1111-1111-1111-111111111111&skill=Reading",
  );
});

test("two Reading bands appear in chronological order", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({
        reading: [
          { date: "2026-01-01T00:00:00Z", band: 6.0 },
          { date: "2026-02-01T00:00:00Z", band: 7.0 },
        ],
      }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(withCors([])),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({})),
  );

  await openExamProgress(page);
  await page.getByRole("tab", { name: "Reading" }).click(); // skill pill if role=tab; else getByRole('button')

  const points = page.locator("[data-testid^=trend-point-]");
  await expect(points).toHaveCount(2);
  await expect(points.nth(0)).toContainText("6.0");
  await expect(points.nth(1)).toContainText("7.0");
});

test("weak-areas failure still shows progress content", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({ reading: [{ date: "2026-03-01T00:00:00Z", band: 6.0 }] }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(
      withCors([
        {
          sessionId: "22222222-2222-2222-2222-222222222222",
          skill: "reading",
          examType: "academic",
          bandScore: 6.0,
          date: "2026-03-01T00:00:00Z",
        },
      ]),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({ error: "boom" }, 500)),
  );

  await openExamProgress(page);
  await expect(page.getByText("6.0").first()).toBeVisible();
  // Soft-fail copy — match whatever Alert text the panel uses
  await expect(page.getByText(/weak area/i)).toBeVisible();
});
```

Align skill-selector query with the actual control (`role="tab"` vs `button`). Align soft-fail assertion with final Alert copy.

- [ ] **Step 2: Run E2E**

```bash
cd "services/frontend"
npm run test:e2e -- test/e2e/exam-progress.spec.ts
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add services/frontend/test/e2e/exam-progress.spec.ts
git commit -m "test(frontend): mocked E2E for Exam Progress tab"
```

---

### Task 9: Gated live E2E smoke (`E2E_LIVE_EXAM=1`)

**Files:**
- Create: `services/frontend/test/e2e/exam-progress-live.spec.ts`

**Interfaces:**
- Consumes: real gateway+exam when flag set; otherwise `test.skip`

- [ ] **Step 1: Write gated live suite**

```typescript
import { test, expect } from "./fixtures/auth";

const live = !!process.env.E2E_LIVE_EXAM;

test.describe("Exam Progress live smoke", () => {
  test.skip(!live, "Set E2E_LIVE_EXAM=1 with gateway+exam running");

  test("after one completed exam, score appears on Exam Progress", async ({
    page,
  }) => {
    // Reuse the shortest existing real Reading submit path from
    // reading-exam.spec.ts helpers if extractable; otherwise document
    // manual seed steps in a comment and assert against seeded user.
    // Minimum: complete/submit one Reading exam → goto /profile →
    // Exam Progress → expect band text visible in chart/list.
    await page.goto("/profile");
    await page.getByRole("tab", { name: "Exam Progress" }).click();
    await expect(page.getByTestId("exam-progress-empty-cta")).toHaveCount(0);
    await expect(page.locator("[data-testid^=trend-point-]").first()).toBeVisible({
      timeout: 30_000,
    });
  });

  test("two Reading exams show chronological 6.0 then 7.0", async ({ page }) => {
    // Requires two real completions or DB seed with those bands.
    // Assert trend-point-0 contains 6.0 and trend-point-1 contains 7.0.
  });
});
```

If extracting a full live Reading completion is too heavy for this ticket, keep the skip gate and implement the first live test by seeding via exam history SQL/API in the live environment — still **not** mocked `page.route`. Document in file header:

```
# Run: E2E_LIVE_EXAM=1 npm run test:e2e -- test/e2e/exam-progress-live.spec.ts
# Requires: gateway :8080, exam service, paid test user cookie from fixtures/auth
```

- [ ] **Step 2: Confirm skip without flag**

```bash
cd "services/frontend"
npm run test:e2e -- test/e2e/exam-progress-live.spec.ts
```

Expected: skipped (not failed).

- [ ] **Step 3: Commit**

```bash
git add services/frontend/test/e2e/exam-progress-live.spec.ts
git commit -m "test(frontend): gated live E2E smoke for Exam Progress"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Opportunities \| Exam Progress tabs | Task 7 |
| Chart.js per-skill trends (skill selector) | Task 6 |
| Weak areas + Practise Now → `/exam` | Task 6 |
| Recent 5 + View Results with sessionId | Tasks 1, 3, 6 |
| Empty CTA copy + `/exam` | Tasks 6, 8 |
| Estimated band + disclaimer + `roundToBand` | Tasks 4, 6 |
| History `sessionId` | Task 1 |
| Result IDOR owner check | Task 2 |
| Per-resource fetch errors | Tasks 5, 6, 8 |
| Mocked E2E + gated live hybrid | Tasks 8–9 |
| R/L sessionStorage gap out of scope | Documented; links still emitted |

No TBD placeholders remain for locked decisions. Live test bodies may need environment-specific seed helpers at implementation time — keep the gate and assert real (non-routed) responses.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-08-08-goa-062-exam-progress-tab.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — run tasks in this session with executing-plans checkpoints  

Which approach?

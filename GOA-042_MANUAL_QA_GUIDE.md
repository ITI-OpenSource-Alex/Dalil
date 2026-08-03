# GOA-042 Manual QA Guide — Speaking Interface Polish (Waveform + Session History)

**Scope:** Manual test plan for the waveform visualiser, `/speaking/history` list, session detail view, band trend chart, and share feature.
**Grounded against actual implementation** (file paths, selectors, endpoints, and response shapes below are taken directly from the shipped code, not inferred).
**No code was modified to produce this document.**

---

## 0. How this document is organized

- **§1** — Global prerequisites shared by every test below.
- **§2–§6** — One section per Acceptance Criterion, each covering the 13 requested sub-items (prerequisites, navigation, numbered steps, expected results, network requests, UI, storage, DB, logs, edge cases, failure scenarios, browser compatibility, responsive checks).
- **§7–§15** — The specific deep-verification techniques requested (waveform authenticity, canvas inspection, RAF verification, AnalyserNode verification, mic stream inspection, trend-chart correctness, ordering, cross-context share verification, API-vs-UI matching).
- **§16** — Full checklist.
- **§17** — What cannot be manually verified, and why.

---

## 1. Global Prerequisites

### 1.1 Two independent test tracks

The feature has two independently testable halves. Testing them separately is faster and isolates failures correctly:

| Track | Covers | Minimum stack |
|---|---|---|
| **A — Live recording** | AC1 (waveform) | Frontend + `speaking` service + `speech` (STT) service + `orchestration` service + Postgres + real Anthropic/ElevenLabs keys |
| **B — History/Detail/Trend/Share** | AC2–AC5 | Frontend + `speaking` service + Postgres only (rows can be seeded directly via SQL — no live recording needed) |

### 1.2 Services that must be running

**Track A (full live session):**
```
docker compose up -d postgres speaking speech orchestration prometheus
```
- `postgres` — `speaking_db` database (created by `infra/docker/postgres/init-databases.sql`)
- `speaking` — Go service, port **8082**, depends on `prometheus` (`docker-compose.yml`)
- `speech` — STT sidecar, port 8086 (`SPEECH_SERVICE_URL=http://speech:8086`)
- `orchestration` — issues the `speaking_url` SSE event that the chat UI listens for
- Frontend dev server: `cd services/frontend && npm run dev` (port 3000)

**Track B (history/detail/trend/share only):**
```
docker compose up -d postgres speaking
cd services/frontend && npm run dev
```
No `speech`/`orchestration`/`speaking-service-real-recording` needed — seed rows directly (see §1.5) and test the pages against them.

### 1.3 Required environment variables

| Variable | Where | Required for |
|---|---|---|
| `NEXT_PUBLIC_SPEAKING_API_URL` | Frontend | Overrides the default `http://localhost:8082` in `lib/speaking-api.ts:5`. **Not documented in any `.env.example`** — if unset, the default is used, which is correct for local Docker Compose, but a tester should be aware there is no `.env.example` entry to cross-check against. |
| `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY` | `speaking` service | 4-agent evaluation swarm (Track A only) |
| `ELEVENLABS_API_KEY` | `speaking` service | TTS playback after evaluation (Track A only) |
| `SPEECH_SERVICE_URL` | `speaking` service | Defaults to `http://speech:8086` inside compose |

No env var gates Track B — the `/sessions*` endpoints have **no authentication** (confirmed: `sessions_handler.go` has no API-key or JWT check, only CORS wrapping in `cors.go`). This is itself worth flagging to the team as a security gap, not a testing blocker — see §12.

### 1.4 Required browser permissions

- **Microphone permission** for `http://localhost:3000` — required only for Track A (AC1). Chrome: `chrome://settings/content/microphone`, or grant via the permission prompt on first "Start Speaking" click.
- **Clipboard read/write permission** — needed to verify the Share button's clipboard content in §6 and §12. Chrome: site settings → Clipboard → Allow. (Playwright automates this with `context.grantPermissions(["clipboard-read", "clipboard-write"])`; manually, Chrome will prompt or silently allow depending on the trigger being a real user gesture.)

### 1.5 Required database data (seeding for Track B)

`CURRENT_USER_ID` is a **hardcoded placeholder**, defined once in `services/frontend/lib/current-user.ts`:
```ts
export const CURRENT_USER_ID = "user-lina";
```
Every page in this feature (history list, detail) queries with this exact user id. To seed test data without running a live session:
```sql
INSERT INTO speaking_sessions (id, user_id, question_prompt, question_type, transcript, evaluation, overall_band, created_at)
VALUES (
  gen_random_uuid(), 'user-lina',
  'Describe a memorable journey you have taken.', 'part2',
  'It was a long trip to the mountains with my family...',
  '{"Fluency and Coherence":{"criterion":"Fluency and Coherence","band":7.0,"feedback":"Good pacing."},
    "Lexical Resource":{"criterion":"Lexical Resource","band":6.5,"feedback":"Varied vocabulary."},
    "Grammatical Range and Accuracy":{"criterion":"Grammatical Range and Accuracy","band":7.5,"feedback":"Complex structures used well."},
    "Pronunciation":{"criterion":"Pronunciation","band":7.0,"feedback":"Clear articulation."}}'::jsonb,
  7.0, NOW()
);
```
**Important:** the `evaluation` JSONB keys are the swarm's **long-form dimension names** (`"Fluency and Coherence"`, `"Lexical Resource"`, `"Grammatical Range and Accuracy"`, `"Pronunciation"`) — not `fluency`/`lexical`/`grammar`/`pronunciation`. The frontend's `extractCriteriaScores()` (`lib/speaking-format.ts`) maps these long-form keys to the short UI keys. Seeding with the wrong key names will silently produce all-zero bands in the UI with no error — a real trap worth testing deliberately (see §5.10).

For the trend chart (AC4), seed **at least 10 rows** with varying `created_at` timestamps and `overall_band` values to test the "last 10" slicing logic (§13).

### 1.6 Required accounts

None. There is no login/auth gate anywhere in this feature (see §1.3). `/speaking/history` is *listed* in `middleware.ts`'s protected-route matcher, but the actual redirect logic is commented out in the current codebase (`middleware.ts:16-18`), so it does not currently enforce authentication even though it's configured to. Do not expect a login prompt.

---

## 2. AC1 — Real-time waveform during recording (Web Audio API AnalyserNode)

### 2.1 Prerequisites
- Track A stack running (§1.2).
- Microphone permission granted for `localhost:3000`.
- A real or virtual microphone input device available (or Chrome's `--use-fake-device-for-media-stream` flag for a synthetic tone, same as the project's own Playwright config).

### 2.2 Navigation steps (every click from app open)
1. Open `http://localhost:3000/chat` in the browser.
2. Locate the message input bar at the bottom of the page.
3. Click the **microphone icon button** (has `title="Speaking Practice"`, no visible text label — it's an icon-only button next to the send button, per `components/chat/chat-input.tsx:73-80`).
4. The Speaking Practice panel slides open (`data-testid="speaking-panel"`).
5. Click the **"Start Speaking"** button (`data-testid="start-speaking-button"`, green, mic icon).

### 2.3 Numbered manual test steps

**Step 1.** Click the mic icon in the chat input bar.
**Expected:** The panel titled "Speaking Practice" appears with status text "Status: idle" and a "Start Speaking" button.

**Step 2.** Click "Start Speaking".
**Expected:** Chrome shows a microphone permission prompt (first time only). Status text changes to "Status: listening" immediately (this happens client-side before any network round trip — `chat-shell.tsx`'s `startSpeaking()` sets state synchronously).

**Step 3.** Grant microphone permission if prompted.
**Expected:** No visible change yet — this priming `getUserMedia()` call is immediately stopped again (`chat-shell.tsx`: the priming stream's tracks are stopped right after acquisition, by design, to avoid a leaked mic indicator).

**Step 4.** Wait for the WebSocket to connect (a few hundred ms to a few seconds depending on `orchestration` + `speaking` service response time).
**Expected:** Once the WS reaches `"connected"`, `AudioRecorder.start()` resolves and the waveform canvas (`data-testid="waveform-canvas"`) appears below the transcript box, above the Start/Stop buttons. The canvas begins animating — a horizontal line reacting to your voice, drawn in emerald green (`#059669`).

**Step 5.** Speak into the microphone at varying volume.
**Expected:** The waveform's amplitude visibly increases with louder speech and flattens toward the horizontal midline during silence.

**Step 6.** Click "Stop" (`data-testid="stop-speaking-button"`).
**Expected:** The waveform canvas disappears immediately (component unmounts when `state !== "listening"`). Status changes to "transcribing", then "evaluating", then "done".

### 2.4 Network requests expected in DevTools

| Step | Method | Endpoint | Expected status | Notes |
|---|---|---|---|---|
| Chat message triggering speaking | POST | `/api/chat` (Next.js route) | 200, SSE stream | Contains a `speaking_url` event with a `wsUrl` field |
| WebSocket | `GET` (upgrade) | `ws://.../ws` (URL from the SSE event) | `101 Switching Protocols` | Visible under DevTools → Network → WS filter. Binary frames flow both directions (audio out, TTS in). |
| N/A | — | No REST calls are made for the waveform itself | — | The waveform is 100% client-side (`AnalyserNode` reads local audio); it makes **zero** network requests. |

### 2.5 UI appearance
- Canvas element, default styling `h-12 w-full rounded-lg bg-[#FAFBF9]` (light background, ~48px tall, full width of the panel).
- `aria-hidden="true"` on the canvas — screen readers will not announce it (correct, since the "Status: listening" text is the accessible equivalent).
- A separate pulsing red dot indicator remains visible alongside the waveform (pre-existing UI element, unaffected by this feature).

### 2.6 localStorage / sessionStorage
**None.** This feature does not read or write `localStorage` or `sessionStorage` at any point. (Do not confuse with the unrelated Exam feature, which does use `sessionStorage` for `active_exam_session` — that is a different feature entirely.)

### 2.7 Database writes
None during recording. The session row is written **after** evaluation completes, asynchronously, by the Go backend (`speaking` service's `runEvaluationAndTTS`, not part of this ticket's own code but consumed by it). Confirm via:
```sql
SELECT id, user_id, overall_band, created_at FROM speaking_sessions ORDER BY created_at DESC LIMIT 1;
```

### 2.8 Logs to check
- **Browser console:** no errors. If `useAudioVisualizer` fails to construct the Web Audio graph, it logs `"useAudioVisualizer: failed to initialize Web Audio graph"` and the canvas silently does not render (graceful degradation, not a crash).
- **Backend (`speaking` service) logs:** `"New WebSocket connection established"`, `"Session initialized successfully"` on connect.

### 2.9 Edge cases to test
- Deny microphone permission → panel should not crash; waveform never appears; verify no unhandled promise rejection in console.
- Click Start, then immediately click Stop before the WS reaches "connected" → waveform should never flash on, and no orphaned `AudioContext` should remain (verify via §9).
- Rapidly click Start/Stop several times in succession → no duplicate/overlapping `AudioContext` instances (check `chrome://media-internals` — see §9).
- Resize the browser window / panel while recording → canvas should resize cleanly via its internal `ResizeObserver`, no stretched or blank canvas.
- Switch mic input device mid-recording (via OS settings) → not explicitly handled by this feature; verify it doesn't hard-crash (acceptable to just stop animating).

### 2.10 Failure scenarios to test
- Close the browser tab while `state === "listening"` → mic indicator (browser tab icon) should turn off; verify via `chrome://settings/content/microphone` "in use" indicator or the tab's mic icon disappearing.
- Click the panel's **X (close) button** (`data-testid="close-speaking-button"`) while recording → per `chat-shell.tsx`, this now explicitly calls `recorderRef.current?.stop()`, so the mic must stop. This was a bug fixed during implementation — verify it doesn't regress (mic indicator must turn off on close, not just on Stop).
- Simulate WS error (e.g., stop the `speaking` service mid-session) → state should return to "idle"; waveform must disappear (state leaves "listening").

### 2.11 Browser compatibility
- **Chrome/Edge (Chromium):** fully supported, primary test target.
- **Firefox:** `AnalyserNode` and `getUserMedia` are supported; verify manually — no code path is Chromium-specific in `useAudioVisualizer.ts`.
- **Safari:** `AudioContext` may start in a `"suspended"` state even after a user gesture. Code defensively calls `audioContext.resume()` in `useAudioVisualizer.ts` — verify the waveform actually animates on Safari/iOS and doesn't silently stay flat due to a suspended context.
- **Unsupported browsers** (no `AudioContext`): `isSupported` check in `useAudioVisualizer.ts` returns false and `WaveformCanvas` renders `null` — verify the rest of the recording flow (transcript, evaluation) still works with the waveform simply absent, no crash.

### 2.12 Responsive / mobile checks
- At narrow viewport widths (375px), the panel and canvas should remain full-width and not overflow horizontally.
- On real mobile Safari/Chrome, microphone permission prompts differ from desktop — verify the flow doesn't break at these OS-level permission dialogs.
- Note: `getUserMedia` requires a secure context (HTTPS or localhost) — testing on a real mobile device against a non-localhost dev server will fail unless served over HTTPS or via a tunnel (e.g., ngrok).

---

## 3. AC2 — Session history page at `/speaking/history`

### 3.1 Prerequisites
Track B stack (§1.2) + at least one seeded row for `user_id = 'user-lina'` (§1.5).

### 3.2 Navigation steps
1. Open `http://localhost:3000/chat` (or any page).
2. Open the left sidebar (always visible on desktop; hamburger menu on mobile).
3. Click **"Speaking History"** nav item (`components/ui/sidebar.tsx` — added between "IELTS" and "CV Review"), which links to `/speaking/history`.
   — *Or* navigate directly to `http://localhost:3000/speaking/history`.

### 3.3 Numbered manual test steps

**Step 1.** Navigate to `/speaking/history` with ≥1 seeded session.
**Expected:** Page renders with header "Speaking History" (badge "Speaking Practice" above it), a "Practice Again" button linking to `/chat`, then (if ≥2 sessions) the trend chart, then the session list below it.

**Step 2.** Observe the list.
**Expected:** Each row shows: truncated `question_prompt` text, a bullet-separated `formatSessionDate(created_at)` (e.g. "Jul 20, 2026") and `question_type` (e.g. "part2"), and a right-aligned "Band" badge showing `overall_band`.

**Step 3.** Hover a row.
**Expected:** Border and background tint change (`hover:border-emerald-200 hover:bg-emerald-50/40`), confirming it's an interactive link, not static text.

### 3.4 Network requests

| Method | Endpoint | Expected status | Request | Response |
|---|---|---|---|---|
| GET | `http://localhost:8082/sessions?userId=user-lina` | 200 | none (query param only) | JSON array of `{id, question_prompt, question_type, overall_band, created_at}` — see `sessionSummaryResponse` in `sessions_handler.go:14-21` |
| OPTIONS | same URL | 204 | CORS preflight — check response headers include `Access-Control-Allow-Origin: *` | empty body |

Verify in DevTools Network tab: the request is `no-store` cached (`lib/speaking-api.ts` sets `cache: "no-store"`), so it should re-fire on every page load/navigation, never served from disk cache.

### 3.5 UI appearance
- **Loading state:** two pulse-animated gray skeleton blocks (one tall for the chart area, three short for list rows) — `HistoryLoadingSkeleton` in `app/speaking/history/page.tsx`.
- **Empty state** (0 sessions): "No speaking sessions yet — start practicing to build your history." + "Start a Session" button.
- **Error state** (backend unreachable): red-bordered panel with the error message and a "Retry" button that re-fires the same request.
- **Success state:** trend chart (if ≥2 sessions) + list.

### 3.6 localStorage / sessionStorage
None used.

### 3.7 Database writes
None — this is a read-only page.

### 3.8 Logs
- Browser console: none expected on success. On fetch failure, `useSessionHistory` sets an error message from the caught exception — check it's a human-readable string, not `"[object Object]"`.
- Backend logs on error: `"Failed to list speaking sessions"` with `user_id` field (`sessions_handler.go:82`).

### 3.9 Edge cases
- Exactly 0 sessions → empty state, no chart section rendered at all.
- Exactly 1 session → list renders, but chart shows its own "insufficient data" placeholder (not the empty-history empty state — these are two different empty states, verify they don't collide).
- A session whose `question_prompt` is very long → verify `truncate` CSS class actually clips it with ellipsis, doesn't break layout.
- Sessions for a *different* `user_id` in the DB → must **not** appear in the list (verify the `WHERE user_id=$1` filter in `ListByUser`).

### 3.10 Failure scenarios
- Stop the `speaking` service entirely → error state with Retry button; clicking Retry after restarting the service should recover without a full page reload.
- Malformed/unreachable `NEXT_PUBLIC_SPEAKING_API_URL` → same error path, verify no unhandled promise rejection crashes the page.

### 3.11 Browser compatibility
No feature-specific APIs here beyond `fetch`; universally supported.

### 3.12 Responsive / mobile checks
- At 375px width: list rows should stack their content sensibly (prompt + date on top, band badge does not overflow off-screen).
- Sidebar collapses to hamburger menu; confirm "Speaking History" is still reachable via the mobile drawer.

---

## 4. AC3 — Clicking a session shows full evaluation breakdown with per-criterion scores

### 4.1 Prerequisites
Same as §3.1, plus knowledge of the exact seeded `evaluation` JSON so you can verify displayed numbers against source data.

### 4.2 Navigation steps
1. From `/speaking/history`, click any session row.
2. Browser navigates to `/speaking/history/{id}` where `{id}` is the session's UUID.

### 4.3 Numbered manual test steps

**Step 1.** Click a session row on the history list.
**Expected:** URL changes to `/speaking/history/<uuid>`; a "← Back to Session History" link appears at the top.

**Step 2.** Wait for the detail page to load.
**Expected:** Card shows: `question_type` badge, `question_prompt` as the heading, `formatSessionDateTime(created_at)` (includes time, e.g. "Jul 20, 2026, 10:00 AM" — distinct from the list page's date-only format), and a "Share" button.

**Step 3.** Below that, the evaluation breakdown card appears: "IELTS Speaking Band Score" header, a large circular badge with the overall band number, then four criterion rows in this **exact order**: "Fluency & Coherence", "Lexical Resource", "Grammatical Range", "Pronunciation Accuracy" (`evaluation-breakdown.tsx`), each with a "Band {n}" label and an animated fill bar sized to `(score / 9) * 100%`.

**Step 4.** Below the evaluation card, a "Transcript" section with a `+`/`−` toggle button.
**Expected:** Collapsed by default; clicking toggles the raw transcript text visible, `aria-expanded` attribute flips correctly.

### 4.4 Network requests

| Method | Endpoint | Expected status | Notes |
|---|---|---|---|
| GET | `http://localhost:8082/sessions/{id}?userId=user-lina` | 200 | Response: `{id, question_prompt, question_type, transcript, evaluation, overall_band, created_at}` — `sessionDetailResponse` in `sessions_handler.go:27-35`. `evaluation` is the **raw** JSONB, keyed by long-form criterion names. |
| GET (unknown id) | `.../sessions/{bad-id}?userId=user-lina` | 404 | `{"Session not found"}` (plain text body via `http.Error`, not JSON) |

### 4.5 UI appearance
- Overall band badge: green circle, white bold text, e.g. "7".
- Per-criterion bars: light gray track (`bg-[#F0F3EF]`), emerald fill, animated width transition on mount (framer-motion).
- No "Expert Feedback" quote block on this page — the seeded/persisted `evaluation` JSONB does **not** include an `overall_feedback` string (only per-criterion `feedback`, which this component does not currently surface). The `EvaluationBreakdown` component's `feedback` prop is simply omitted here, so that quote section never renders on the history detail or public share pages (it *does* appear in the live chat panel, which passes `feedback` from the live WS event). This is expected, not a bug — verify no empty/broken feedback section appears.

### 4.6 localStorage / sessionStorage
None.

### 4.7 Database writes
None — read-only page.

### 4.8 Logs
Backend: `"Failed to fetch speaking session"` (500) or a plain 404 with no log line for the not-found case (by design — not-found is not logged as an error, only unexpected DB errors are, per `sessions_handler.go:105-113`).

### 4.9 Edge cases
- Navigate directly to `/speaking/history/<valid-uuid-belonging-to-a-different-user>` → per `HandleGetSession`, a `userId` mismatch returns 404, **not** 403 (deliberate, to avoid leaking which IDs exist). Verify the UI shows the same "not found" treatment as a truly nonexistent ID.
- A session whose `evaluation` JSONB is missing one of the four expected criterion keys (e.g., partial/timed-out agent) → `extractCriteriaScores()` defaults missing keys to `0`. Verify the UI shows "Band 0" for that criterion rather than crashing or omitting the row.
- Copy-paste a syntactically invalid UUID into the URL → verify graceful error handling, not a raw stack trace.

### 4.10 Failure scenarios
- Stop `speaking` service after the list loads but before clicking through → detail page should show its own error+retry state, independent of the list page's state.
- Slow network (DevTools → Network → Throttle "Slow 3G") → loading skeleton (`animate-pulse` gray block) should show for the duration, no flash of empty content.

### 4.11 Browser compatibility
No special APIs; universal.

### 4.12 Responsive / mobile checks
- At 375px: the criterion rows and overall-band badge should remain legible; verify the badge+label row doesn't wrap awkwardly.
- Transcript toggle button must remain tappable (adequate touch target) on mobile.

---

## 5. AC4 — Band score trend chart (last 10 sessions)

### 5.1 Prerequisites
Track B stack + **at least 10 seeded sessions** with distinct `created_at` values spanning several days, and varying `overall_band` values, to meaningfully test the "last 10" and ordering logic. Seed 12–15 to properly test the truncation boundary.

### 5.2 Navigation steps
Same as §3.2 — the chart renders inline at the top of `/speaking/history`, above the session list. No separate navigation.

### 5.3 Numbered manual test steps

**Step 1.** With ≥2 sessions seeded, load `/speaking/history`.
**Expected:** A card titled "Band Trend" appears above the list, containing a Chart.js line chart.

**Step 2.** Inspect the chart visually.
**Expected:** X-axis shows short dates (`formatSessionDate`), Y-axis fixed 0–9 with integer ticks, a single emerald line with visible point markers, no legend (legend is explicitly disabled — `plugins: { legend: { display: false } }`).

**Step 3.** Hover a data point.
**Expected:** Chart.js default tooltip appears showing the value.

**Step 4.** With exactly 1 session, reload the page.
**Expected:** No chart renders at all — instead a card reading "Complete more sessions to see your band trend."

**Step 5.** With 0 sessions, reload.
**Expected:** Neither the chart nor its placeholder appears — the page's own history-empty-state takes over entirely (these are two distinct empty states; only one should ever be visible at a time).

### 5.4 Network requests
No separate request — the chart consumes the **same** `GET /sessions?userId=...` response already fetched for the list (`useSessionHistory` is called once in `app/speaking/history/page.tsx` and both `<BandTrendChart>` and `<SessionHistoryList>` receive the same `sessions` array as props). Verify in DevTools that reloading the page fires exactly **one** `/sessions` request, not two.

### 5.5 UI appearance
Chart.js canvas, ~256px tall (`h-64`), full width of its card.

### 5.6 localStorage / sessionStorage
None.

### 5.7 Database writes
None.

### 5.8 Logs
None expected under normal operation.

### 5.9 Edge cases
- Exactly 10 sessions → all 10 should render, oldest-to-newest left to right.
- Exactly 11 sessions → the **oldest** one must be dropped, not the newest (verify against §13's method).
- All sessions on the same `overall_band` value → line should render flat, not collapse/error.
- A session with `overall_band = 0` (e.g. from an all-timed-out evaluation) → should still plot at y=0, not be excluded.

### 5.10 Failure scenarios
- A seeded row with a malformed `evaluation` JSONB that fails to parse — this affects the detail page, not the chart (the chart only reads `overall_band`, a plain SQL column, not the JSONB). Confirm the chart is unaffected by evaluation JSONB corruption.

### 5.11 Browser compatibility
Chart.js/Canvas 2D — universally supported on evergreen browsers.

### 5.12 Responsive / mobile checks
- At narrow widths, Chart.js's `responsive: true, maintainAspectRatio: false` should keep the chart within its fixed-height container without horizontal overflow — verify no horizontal scrollbar appears on the page.

---

## 6. AC5 — Share button (public URL, no auth required)

### 6.1 Prerequisites
Track B stack + a seeded session with a known UUID + clipboard permissions granted (§1.4).

### 6.2 Navigation steps
1. From a session detail page (`/speaking/history/{id}`), locate the **"Share"** button next to the date/badge.
2. Click it.

### 6.3 Numbered manual test steps

**Step 1.** Click "Share" for the first time on a given session.
**Expected:** Button text changes to "Generating link..." briefly, then "Copied!" with a checkmark icon (replacing the share icon).

**Step 2.** Immediately try pasting (Ctrl+V) into any text field.
**Expected:** Pasted content is exactly `http://localhost:3000/speaking/share/<share_token>` — a 40-character lowercase hex token (160-bit random, per `generateShareToken()` in `services/speaking/db/repository.go`).

**Step 3.** Wait ~2 seconds.
**Expected:** Button reverts to "Share" (idle state resets after the `useClipboard` hook's timeout).

**Step 4.** Click "Share" again on the *same* session.
**Expected:** Same URL/token is returned — **idempotent**, not a new token each time (verify via Step 2's paste matching exactly).

### 6.4 Network requests

| Method | Endpoint | Expected status | Request body | Response |
|---|---|---|---|---|
| POST | `http://localhost:8082/sessions/{id}/share` | 200 | none | `{"share_token": "<40-hex-chars>"}` |
| OPTIONS | same URL | 204 | — | CORS preflight |

Verify: the field name is `share_token` (snake_case) — this was deliberately corrected during implementation from an initial `shareToken` inconsistency; if you see camelCase in the response, that is a regression.

### 6.5 UI appearance
- Idle: "Share" text + share icon.
- Loading: "Generating link..." (button disabled).
- Success: "Copied!" + check icon.
- Failure (clipboard unavailable): a secondary `<input readonly>` field appears below the button showing the URL directly (manual-select fallback), plus explanatory text "Couldn't copy automatically — copy the link below:".

### 6.6 localStorage / sessionStorage
None — the minted token is not cached client-side; every "Share" click re-requests it from the backend (which returns the same token idempotently server-side).

### 6.7 Database writes
```sql
SELECT share_token FROM speaking_sessions WHERE id = '<id>';
```
Should be populated (was `NULL` before the first Share click) and stay stable across repeated clicks.

### 6.8 Logs
Backend: `"Failed to create share link"` only on unexpected DB errors; a 404 for a nonexistent session id is not logged as an error.

### 6.9 Edge cases
- Two different sessions shared back-to-back → tokens must differ between sessions.
- Share a session, then re-fetch it via `GET /sessions/{id}` → `share_token` is **not** included in the authenticated detail response shape (`sessionDetailResponse` has no such field) — this is correct; the token is only ever returned by the `/share` POST response itself.
- Click Share on the same session from two different browser tabs at nearly the same time → both should end up with the identical token (server-side `COALESCE` idempotency in `CreateShareToken`), not two different tokens or a duplicate-key error.

### 6.10 Failure scenarios
- Simulate the POST failing (stop `speaking` service, click Share) → an inline red error message should appear near the button; the button should not remain stuck in "Generating link..." forever.
- Deny clipboard permission (or test in a context Chrome considers insecure) → the manual-select `<input>` fallback must appear; verify the URL value is still correct even though auto-copy failed.

### 6.11 Browser compatibility
- `navigator.clipboard.writeText` requires a **secure context** (HTTPS or `localhost`). Testing over plain HTTP on a LAN IP will always hit the fallback path — this is expected behavior, not a bug, per `useClipboard.ts`'s `window.isSecureContext` check.
- Safari has historically stricter clipboard-permission requirements tied to direct user gesture — verify the click-triggered copy still works there.

### 6.12 Responsive / mobile checks
- On mobile, verify the fallback `<input readonly>` is easily selectable via long-press/tap-and-hold, since mobile clipboard-from-JS support is less consistent than desktop.

---

## 7–15. Deep Verification Techniques

### 7 (= req. 14). Verifying the waveform uses **live microphone data**, not a fake animation

1. Open DevTools → Sources, set a breakpoint inside `waveform-canvas.tsx`'s `draw()` function at the line `analyser.getByteTimeDomainData(dataArray)`.
2. Start a speaking session, let it hit the breakpoint, inspect `dataArray` in the console: `Array.from(dataArray)`.
3. **Definitive live-data test:** stay completely silent for 2 seconds, note the values (should hover tightly around 128, the silence midpoint). Then clap loudly near the mic and immediately re-inspect — values should spike toward 0/255 at the extremes. A fake/canned animation would not react to real-world audio timing.
4. Cross-check: mute the OS microphone input (not the browser tab) mid-session — the waveform should flatten to a near-constant line (silence), proving it's reading a real audio device, not a synthetic oscillator.
5. Confirm the analyser is attached to the *same* stream `AudioRecorder` uses for transcription (not a second, independently-requested stream) — Chrome's tab microphone indicator should show **exactly one** active use per session, not two overlapping `getUserMedia` grants. Check via `chrome://settings/content/microphone` "Currently in use" listing, or the single microphone icon in the tab strip.

### 8 (= req. 19). Inspecting the Canvas waveform via DevTools

1. DevTools → Elements, find `<canvas data-testid="waveform-canvas">`.
2. Right-click it in the Elements panel → **no built-in "inspect canvas" in stock Chrome**, but you can:
   - Switch DevTools to the **Console** and run:
     ```js
     const c = document.querySelector('[data-testid="waveform-canvas"]');
     const ctx = c.getContext('2d');
     const frame = ctx.getImageData(0, 0, c.width, c.height);
     console.log(frame.data.filter(v => v !== 0).length); // non-zero byte count
     ```
     This is the exact technique the project's own Playwright test (`speaking-system.spec.ts`) uses to assert the canvas is animating.
   - Right-click the canvas element → **"Capture node screenshot"** to visually confirm a waveform line is actually drawn, not a blank canvas.
3. Re-run the `getImageData` snippet twice, a few hundred ms apart, and diff the resulting `Uint8ClampedArray` — if the two frames are byte-identical while actively recording, the canvas is **not** animating (a real defect).

### 9 (= req. 20). Verifying `requestAnimationFrame` is running continuously

1. DevTools → **Performance** tab → click Record → speak for ~3 seconds → Stop.
2. In the flame chart, filter/search for `"draw"` or look at the **Frames** row — you should see a `requestAnimationFrame` callback firing on (almost) every frame at your display's refresh rate (typically ~60/sec, so ~180 calls over 3 seconds).
3. Alternative — DevTools Console:
   ```js
   let n = 0;
   const orig = window.requestAnimationFrame;
   window.requestAnimationFrame = (cb) => { n++; return orig(cb); };
   setTimeout(() => console.log('RAF calls in 2s:', n), 2000);
   ```
   Run this **before** starting the session; expect a count in the hundreds after 2 seconds (not 1, not 0).
4. Stop the recording (click "Stop") and repeat the count-over-2-seconds test — it should now be **zero new calls attributable to the waveform**, confirming `cancelAnimationFrame` correctly tears down the loop in the component's cleanup function (`waveform-canvas.tsx`'s `useEffect` return callback). A stuck RAF loop after unmount is a real leak class of bug to check for here.

### 10 (= req. 21). Verifying `AnalyserNode` is connected correctly

1. Chrome → navigate to `chrome://webrtc-internals` **before** starting a session (this shows the underlying `getUserMedia` stream, not the Web Audio graph directly, but confirms the stream exists and is active).
2. For the Web Audio graph itself, use the DevTools Console while a session is active:
   ```js
   // No direct public API to walk the graph, but you can verify indirectly:
   // 1. Confirm exactly one AudioContext exists by checking for audio processing activity:
   performance.getEntriesByType('resource'); // unrelated; Web Audio isn't resource-timed
   ```
   Since the Web Audio API has no official graph-introspection API, use the **behavioral proof** instead: confirm §7's silence/loud-noise test (proves the analyser is receiving real audio) **and** confirm no audible feedback/echo occurs during recording — since `useAudioVisualizer.ts` deliberately never connects the analyser to `audioContext.destination`, you should **never** hear your own voice echoed back through the speakers while recording (only the post-evaluation TTS feedback audio should play, after Stop). Audible mic feedback during recording would indicate an incorrect `connect()` call.
3. Confirm exactly one `AudioContext` per session: add a temporary console check —
   ```js
   let count = 0;
   const OrigAC = window.AudioContext;
   window.AudioContext = new Proxy(OrigAC, { construct(t, a) { count++; console.log('AudioContext #' + count); return new t(...a); } });
   ```
   Run before starting; expect exactly **one** `"AudioContext #1"` log per recording session, not zero (analyser never attached) and not multiple (leak/duplicate attachment).

### 11 (= req. 22). Manually inspecting the microphone stream in Chrome DevTools

1. Navigate to `chrome://webrtc-internals` in a second tab, **before** starting the speaking session in the first tab.
2. Start the session; the `webrtc-internals` page should show a `getUserMedia` audio track entry appear, with live stats (audio level, sample rate).
3. Alternatively, in the main tab's DevTools Console while recording:
   ```js
   navigator.mediaDevices.enumerateDevices().then(console.log); // lists available devices, confirms permission granted
   ```
   To inspect the *active* stream directly, you'd need a reference to it, which isn't exposed globally by design (encapsulated inside `AudioRecorder`) — this is intentional encapsulation, not a testing gap; the indirect audio-level checks above are the correct verification path.
4. Stop the session and confirm the `webrtc-internals` track entry transitions to "ended"/is removed — proving `track.stop()` was actually called (mic released), not just the UI hidden.

### 12 (= req. 15). Verifying the Chart.js trend uses the last 10 sessions correctly

1. Seed exactly 15 sessions with distinct, known `overall_band` values and `created_at` timestamps 1 day apart (e.g., bands `5.0, 5.5, 6.0, ..., 12.0` — use out-of-range values deliberately if needed purely to make each point uniquely identifiable during this test, then reset).
2. Load `/speaking/history`.
3. Use the **screen-reader-accessible summary** as ground truth — `band-trend-chart.tsx` renders a visually-hidden (`sr-only`) paragraph: *"Band trend over your last N sessions: b1, b2, b3, …"*. Inspect it directly via DevTools Elements (search for the `<p class="sr-only">` inside the chart card) rather than trying to read pixel positions off the canvas.
4. Verify: exactly **10** values are listed, they are the 10 **most recent** by `created_at` (i.e., sessions 6–15 if you seeded 15 in ascending date order), and they appear in **chronological (oldest-to-newest) order**, not database/query order.
5. Cross-check against direct SQL:
   ```sql
   SELECT overall_band FROM speaking_sessions WHERE user_id='user-lina' ORDER BY created_at DESC LIMIT 10;
   ```
   then reverse that list — it must match the `sr-only` summary exactly.
6. This also validates the code path described in `band-trend-chart.tsx`: sort all sessions descending, `slice(0, 10)`, then `.reverse()` for left-to-right chronological display — you're black-box-verifying that exact algorithm via its rendered/accessible output rather than reading the source.

### 13 (= req. 16). Verifying history list ordering

1. Seed 5 sessions with deliberately out-of-order insertion but distinct `created_at` values (e.g., insert the oldest row last).
2. Load `/speaking/history`.
3. Read the dates displayed on each row top-to-bottom; they must be **most-recent-first** (descending `created_at`), matching the backend's `ORDER BY created_at DESC` in `ListByUser` (`services/speaking/db/repository.go`), regardless of insertion order.
4. Directly compare against `SELECT question_prompt, created_at FROM speaking_sessions WHERE user_id='user-lina' ORDER BY created_at DESC;` — the on-screen order must match this query's row order exactly, top to bottom.

### 14 (= req. 17). Verifying the copied Share URL works across contexts

1. On a session detail page, click Share and copy the URL (§6.3).
2. **Incognito window:** Open a new Incognito window (Ctrl+Shift+N), paste the URL, navigate.
   **Expected:** Page loads fully — question prompt, evaluation breakdown, transcript — with **no login prompt or redirect**, since `/speaking/share/*` is deliberately excluded from `middleware.ts`'s protected-route matcher.
3. **Logged-out user:** Since there is no login system integrated into this flow at all currently (§1.6), this is effectively equivalent to step 2 — confirm no cookie/session state from the main window is required.
4. **Different browser:** Paste the same URL into an entirely different browser (e.g., Firefox if you tested in Chrome). Must render identically.
5. **Verify no authenticated UI leaks through:** on the share page, confirm the left Sidebar (with nav items like "Chat", "IELTS", etc.) is **absent** — `app/speaking/share/[token]/page.tsx` is deliberately built as a standalone page with its own minimal header (just the "goa" brand mark), not wrapped in the authenticated app shell. Its presence would indicate the wrong layout was used.
6. **Verify no PII/account data leaks:** inspect the Network response for `GET /sessions/public/{token}` — confirm the JSON body contains **no** `user_id` field anywhere (grep the raw response text for `"user_id"` — it must not appear; `sessionDetailResponse` has no such field by construction).
7. **Negative test:** truncate or alter one character of the copied token and navigate to that URL → must show a "not found" error state, not leak a different user's session or crash.

### 15 (= req. 18). Verifying the evaluation breakdown matches the API response exactly

1. On a session detail page, open DevTools → Network, find the `GET /sessions/{id}` response, and copy the full JSON body (right-click → Copy → Copy response).
2. Parse the `evaluation` field's four keys and their `band` values manually.
3. On screen, read the four displayed "Band {n}" values in order: Fluency & Coherence, Lexical Resource, Grammatical Range, Pronunciation Accuracy.
4. Map using the **actual** key-to-label mapping implemented in `lib/speaking-format.ts`:

   | UI label | JSON key read | Internal short key |
   |---|---|---|
   | Fluency & Coherence | `"Fluency and Coherence"` | `fluency` |
   | Lexical Resource | `"Lexical Resource"` | `lexical` |
   | Grammatical Range | `"Grammatical Range and Accuracy"` | `grammar` |
   | Pronunciation Accuracy | `"Pronunciation"` | `pronunciation` |

5. Confirm each on-screen number equals `Math.round` — actually no rounding is applied; confirm each on-screen number is the **exact** `band` float from the matching JSON key (e.g. JSON `6.5` must display as `6.5`, not `7` or `6`).
6. Also verify the large circular badge at the top equals the top-level `overall_band` field, **not** an average recomputed client-side from the four criteria (the UI does not recompute this — it trusts the server-provided `overall_band` directly).
7. **Regression check:** this exact key-mapping was the subject of a bug found and fixed during implementation (the live chat panel previously read short lowercase keys like `"fluency"` directly from the swarm output, which never matched the swarm's actual long-form keys, silently producing "Band 0" everywhere). Deliberately seed a row using the **wrong** (short) key names and confirm the UI now correctly shows `0` for all four criteria (proving the fallback default still works safely) rather than crashing — then re-seed with correct long-form keys and confirm real values appear.

---

## 16. Complete QA Checklist

### AC1 — Waveform
- [ ] Waveform canvas appears only while `state === "listening"`
- [ ] Waveform reacts to real mic volume (silence vs. loud noise test, §7)
- [ ] Waveform disappears immediately on Stop
- [ ] Waveform disappears immediately on Close (X button) while recording
- [ ] `requestAnimationFrame` loop confirmed running during recording (§9)
- [ ] `requestAnimationFrame` loop confirmed **stopped** after recording ends (§9)
- [ ] No audible echo/feedback during recording (§10)
- [ ] Exactly one `AudioContext` created per session (§10)
- [ ] Mic indicator (tab icon / OS indicator) turns off after Stop
- [ ] Mic indicator turns off after Close-while-recording
- [ ] Rapid Start/Stop clicking does not create overlapping contexts
- [ ] Mic permission denial does not crash the panel
- [ ] Waveform degrades gracefully (no canvas, no crash) when Web Audio API unsupported
- [ ] Canvas `getImageData` shows non-zero pixel values while animating (§8)
- [ ] Two consecutive `getImageData` captures differ while animating (proves motion, not a static frame)
- [ ] Responsive at 375px width, no horizontal overflow

### AC2 — History list
- [ ] `/speaking/history` reachable from sidebar nav
- [ ] `GET /sessions?userId=user-lina` fires exactly once per page load
- [ ] List shows date, topic (`question_prompt`), and overall band per row
- [ ] Empty state shown correctly at 0 sessions
- [ ] Loading skeleton shown during fetch
- [ ] Error + Retry state shown when backend unreachable; Retry actually re-fires the request
- [ ] Rows for other `user_id`s never appear
- [ ] List order matches `ORDER BY created_at DESC` exactly (§13)

### AC3 — Session detail
- [ ] Clicking a row navigates to `/speaking/history/{id}`
- [ ] All four criteria shown, correct labels, correct order
- [ ] Displayed bands match raw API `evaluation` JSON exactly (§15)
- [ ] Overall band badge matches `overall_band`, not a client recomputation
- [ ] Transcript collapsed by default; toggle works; `aria-expanded` correct
- [ ] Unknown/foreign-user session id → 404 UI, not a crash
- [ ] Missing criterion key in JSON → defaults to Band 0, no crash

### AC4 — Trend chart
- [ ] Chart hidden entirely at 0 sessions
- [ ] "Complete more sessions" placeholder shown at exactly 1 session
- [ ] Chart renders at 2+ sessions
- [ ] Exactly last 10 sessions shown when 11+ exist (§12)
- [ ] Chronological (oldest→newest) left-to-right order (§12)
- [ ] Y-axis fixed 0–9
- [ ] `sr-only` accessible summary present and matches visual chart (§12)
- [ ] No duplicate `/sessions` network call caused by the chart
- [ ] No horizontal overflow at narrow viewport widths

### AC5 — Share
- [ ] First click mints a token; `POST /sessions/{id}/share` → 200, `share_token` field (snake_case)
- [ ] Second click on same session returns the **same** token (idempotent)
- [ ] Copied URL format: `{origin}/speaking/share/{token}`
- [ ] Button shows Idle → Generating → Copied → Idle state cycle correctly
- [ ] Clipboard failure shows manual-select `<input readonly>` fallback
- [ ] `share_token` persisted in DB after first share
- [ ] Public page loads in Incognito with no login prompt (§14)
- [ ] Public page loads in a different browser (§14)
- [ ] Public page has no Sidebar / authenticated chrome
- [ ] Public API response contains no `user_id` field
- [ ] Invalid/altered token → not-found state, not a crash or data leak

### Cross-cutting
- [ ] No `localStorage`/`sessionStorage` writes anywhere in this feature
- [ ] `npm run build` succeeds with no errors related to these routes
- [ ] No console errors on any of the 5 pages/flows above under normal operation
- [ ] Backend logs contain expected structured entries for both success and error paths

---

## 17. What cannot be manually verified (and why)

1. **True Web Audio graph topology (node-by-node).** The Web Audio API exposes no public introspection API to enumerate a graph's connections at runtime. §10's technique (silence test, absence of audible feedback, single-AudioContext-per-session check) is the strongest **behavioral proxy** available manually, but it is inference from observed behavior, not a direct assertion that `source.connect(analyser)` was called and `analyser.connect(destination)` was not. Only source-code review or an automated test with instrumented/mocked `AudioContext.prototype.connect` can assert this directly (the project's own unit-level guarantee here is code review, not manual QA).
2. **Exact `fftSize` / analyser configuration value (2048) from the outside.** The visual waveform resolution is influenced by `fftSize`, but there is no way to read this property from a black-box UI test without DevTools script injection reaching into the component's internal ref — which is effectively white-box testing, not manual QA. Confirmed via source (`useAudioVisualizer.ts`) rather than pure UI observation.
3. **The internal `dataArray` reuse-vs-reallocate-per-frame behavior.** The implementation reuses a single `Uint8Array` across frames for performance (avoiding per-frame garbage collection). This is a memory/performance property, not something observable in the rendered UI at all — it requires either a heap profiler session correlated with source knowledge, or code review.
4. **Server-side share-token uniqueness guarantee at scale.** Manual testing can confirm two tokens *look* different across a handful of manual shares, but cannot verify the underlying guarantee (160-bit `crypto/rand` entropy is collision-resistant) — that is a cryptographic/statistical property provable only by code review or long-running automated fuzzing, not manual QA.
5. **Race-condition safety of concurrent "Share" clicks from two tabs (§6.9).** Manual testing can observe the *outcome* (both tabs end up with the same token) but cannot verify *why* it's safe under concurrent database access (the `COALESCE`-based single-statement upsert in `CreateShareToken`) without reading the SQL — a timing-dependent race is inherently hard to force deterministically by hand, and its absence under manual testing is not proof of its absence in production under real concurrent load.
6. **Whether the `/sessions*` endpoints' complete lack of authentication is intentional.** Manual QA can confirm the *behavior* (no auth required, confirmed in §1.3/§1.6) but cannot determine from the running system alone whether this is a deliberate MVP scope decision or an oversight — that requires the product/ticket context, not testing. Flagging it here as a finding, not a "fail."
7. **Automated regression protection.** This document describes manual procedures; it does not itself prevent future regressions. The project's own Playwright suite (`speaking-system.spec.ts`, `speaking-history.spec.ts`, `speaking-history-mocked.spec.ts`) covers a meaningful subset of the above scenarios in an automated, repeatable way — manual testing here should be treated as complementary (especially for the genuinely-hard-to-automate audio/canvas authenticity checks in §7–§11), not a replacement for running that suite.

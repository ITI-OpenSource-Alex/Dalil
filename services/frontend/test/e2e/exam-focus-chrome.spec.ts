import { test, expect, type Page, type Route } from "./fixtures/auth";
import {
  READING_PASSAGES,
  READING_QUESTIONS,
} from "./fixtures/reading-questions";

// Focus chrome is pathname-based (AppShell + isExamFocusPath). These specs
// stub the Gateway the same way reading-exam.spec.ts does so /exam/shell
// stays mounted instead of redirecting to /exam when GET session fails.
const GATEWAY_API_BASE = "http://localhost:8080/api/exam";
const SESSION_ID = "focus-chrome-smoke";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Credentials": "true",
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: corsHeaders(),
    body: JSON.stringify(body),
  });
}

async function withPreflight(
  route: Route,
  handle: (route: Route) => Promise<void>,
) {
  if (route.request().method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders() });
    return;
  }
  await handle(route);
}

const SESSION_RESPONSE = {
  id: SESSION_ID,
  user_id: "00000000-0000-0000-0000-000000000001",
  exam_type: "academic",
  skill_area: "reading",
  status: "in_progress",
  started_at: new Date().toISOString(),
  submitted_at: null,
  time_limit_seconds: 3600,
  remaining_time_seconds: 3600,
  questions: [
    {
      id: "question-set-1",
      book_ref: "focus-chrome",
      test_number: 1,
      exam_type: "academic",
      skill_area: "reading",
      passage_text: READING_PASSAGES.join("---"),
      audio_s3_key: null,
      questions: READING_QUESTIONS,
    },
  ],
};

/** Keep the shell on /exam/shell long enough to assert app chrome is gone. */
async function mockShellSession(page: Page) {
  await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}`, (route) =>
    withPreflight(route, (r) => fulfillJson(r, SESSION_RESPONSE)),
  );
  await page.route(
    `${GATEWAY_API_BASE}/sessions/${SESSION_ID}/heartbeat`,
    (route) => withPreflight(route, (r) => fulfillJson(r, { ok: true })),
  );
}

test.describe("Exam focus chrome", () => {
  test("exam hub still shows main app navigation", async ({ page }) => {
    await page.goto("/exam");
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  });

  test("exam shell hides main app navigation", async ({ page }) => {
    await mockShellSession(page);
    await page.goto(`/exam/shell?session=${SESSION_ID}`);
    await expect(page).toHaveURL(new RegExp(`/exam/shell\\?session=${SESSION_ID}`));

    // Wait until the shell has left the loading state so a failed session
    // load would have already redirected — then assert chrome is still gone.
    await expect(page.getByText("Reading Module")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Open menu" })).toHaveCount(0);
  });
});

import { test, expect, Page } from "./fixtures/auth";

// These tests stub the Speaking Service's REST responses at the network
// layer, so the full history → detail → share flow can be verified with
// real, known data without requiring `docker compose up` (unlike the
// waveform-animation and other backend-gated tests in speaking-system.spec.ts).
//
// Speaking is reached through the Gateway now (GOA-132), not directly on
// :8082 — so these routes must match /api/speaking/*, and the requests carry
// no userId: the Gateway takes it from the JWT. Still a different origin than
// the frontend (localhost:8080 vs localhost:3000), so mocked responses need
// CORS headers or the browser rejects them exactly as it would a real
// cross-origin response missing them.
const SPEAKING_API_BASE = "http://localhost:8080/api/speaking";

function withCors(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    // A wildcard origin is rejected by the browser once the request's
    // credentials mode is "include" (which every speaking-api.ts call uses,
    // per the file-level comment above) -- CORS requires an explicit origin
    // to pair with credentialed requests. Pre-existing bug in this mock
    // helper (present at the last commit before this work), found because it
    // silently broke every test in this file with a CORS error rather than
    // whatever each test actually meant to verify.
    headers: {
      "Access-Control-Allow-Origin": "http://localhost:3000",
      "Access-Control-Allow-Credentials": "true",
    },
    body: JSON.stringify(body),
  };
}

const SESSION_SUMMARY = {
  id: "11111111-1111-1111-1111-111111111111",
  question_prompt: "Describe a memorable journey you have taken.",
  question_type: "part2",
  overall_band: 7.0,
  created_at: "2026-07-20T10:00:00Z",
};

const SESSION_DETAIL = {
  ...SESSION_SUMMARY,
  transcript: "It was a long trip to the mountains with my family...",
  evaluation: {
    "Fluency and Coherence": { criterion: "Fluency and Coherence", band: 7.0, feedback: "Good pacing." },
    "Lexical Resource": { criterion: "Lexical Resource", band: 6.5, feedback: "Varied vocabulary." },
    "Grammatical Range and Accuracy": { criterion: "Grammatical Range and Accuracy", band: 7.5, feedback: "Complex structures used well." },
    Pronunciation: { criterion: "Pronunciation", band: 7.0, feedback: "Clear articulation." },
  },
};

function makeSessions(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `session-${i}`,
    question_prompt: `Practice question ${i}`,
    question_type: "part2",
    overall_band: 5 + (i % 5) * 0.5,
    created_at: new Date(2026, 0, i + 1).toISOString(),
  }));
}

async function mockListSessions(page: Page, sessions: unknown[]) {
  await page.route(`${SPEAKING_API_BASE}/sessions`, (route) =>
    route.fulfill(withCors(sessions)),
  );
}

test.describe("GOA Speaking History (mocked backend)", () => {
  test("clicking a session in the list navigates to its detail view with the correct evaluation breakdown", async ({
    page,
  }) => {
    await mockListSessions(page, [SESSION_SUMMARY]);
    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}`,
      (route) => route.fulfill(withCors(SESSION_DETAIL)),
    );

    await page.goto("/practice/speaking/history");

    await expect(page.getByText(SESSION_SUMMARY.question_prompt)).toBeVisible();
    await expect(page.getByText("7", { exact: true }).first()).toBeVisible();

    await page.getByText(SESSION_SUMMARY.question_prompt).click();

    await expect(page).toHaveURL(`/practice/speaking/history/${SESSION_DETAIL.id}`);
    await expect(page.getByText("IELTS Speaking Band Score")).toBeVisible();

    // Per-criterion scores from the mocked evaluation (bands, not the
    // buggy short-key lookup this refactor fixed).
    await expect(page.getByText("Band 7", { exact: true })).toHaveCount(2); // Fluency + Pronunciation
    await expect(page.getByText("Band 6.5")).toBeVisible(); // Lexical
    await expect(page.getByText("Band 7.5")).toBeVisible(); // Grammar
  });

  test("trend chart's accessible summary reflects exactly the last 10 sessions", async ({
    page,
  }) => {
    await mockListSessions(page, makeSessions(15));

    await page.goto("/practice/speaking/history");

    const summary = page.locator("p.sr-only", {
      hasText: "Band trend over your last",
    });
    await expect(summary).toHaveText(/last 10 sessions/);

    const text = await summary.textContent();
    const values = text?.match(/:\s*(.+)\.$/)?.[1].split(", ") ?? [];
    expect(values).toHaveLength(10);
  });

  test("fewer than 2 sessions shows the insufficient-data placeholder instead of a chart", async ({
    page,
  }) => {
    await mockListSessions(page, makeSessions(1));

    await page.goto("/practice/speaking/history");

    await expect(
      page.getByText("Complete more sessions to see your band trend."),
    ).toBeVisible();
  });

  test("share button copies the correct public URL to the clipboard", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);

    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}`,
      (route) => route.fulfill(withCors(SESSION_DETAIL)),
    );
    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}/share`,
      (route) => route.fulfill(withCors({ share_token: "abc123sharetoken" })),
    );

    await page.goto(`/practice/speaking/history/${SESSION_DETAIL.id}`);
    await page.getByRole("button", { name: "Share" }).click();

    await expect(page.getByRole("button", { name: "Copied!" })).toBeVisible();

    const clipboardText = await page.evaluate(() =>
      navigator.clipboard.readText(),
    );
    expect(clipboardText).toBe(
      `${new URL(page.url()).origin}/speaking/share/abc123sharetoken`,
    );
  });

  test("falls back to a manual-select input when the Clipboard API is unavailable", async ({
    page,
  }) => {
    // Simulate a non-secure-context / unsupported-browser clipboard before
    // any page script runs.
    await page.addInitScript(() => {
      Object.defineProperty(window, "isSecureContext", {
        value: false,
        configurable: true,
      });
    });

    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}`,
      (route) => route.fulfill(withCors(SESSION_DETAIL)),
    );
    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}/share`,
      (route) => route.fulfill(withCors({ share_token: "fallbacktoken" })),
    );

    await page.goto(`/practice/speaking/history/${SESSION_DETAIL.id}`);
    await page.getByRole("button", { name: "Share" }).click();

    const fallbackInput = page.locator("input[readonly]");
    await expect(fallbackInput).toBeVisible();
    await expect(fallbackInput).toHaveValue(
      /\/speaking\/share\/fallbacktoken$/,
    );
  });

  test("history list is keyboard-navigable", async ({ page }) => {
    await mockListSessions(page, [SESSION_SUMMARY]);
    await page.route(
      `${SPEAKING_API_BASE}/sessions/${SESSION_DETAIL.id}`,
      (route) => route.fulfill(withCors(SESSION_DETAIL)),
    );

    await page.goto("/practice/speaking/history");

    const sessionLink = page.getByRole("link", {
      name: new RegExp(SESSION_SUMMARY.question_prompt),
    });
    await sessionLink.focus();
    await expect(sessionLink).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`/practice/speaking/history/${SESSION_DETAIL.id}`);
  });
});

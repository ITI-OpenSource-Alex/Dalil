import { test, expect, type Page } from "@playwright/test";

// Real speaking_url SSE frame, in the exact envelope Orchestration emits
// (see services/orchestration/app/services/client.py:133). Routing /api/chat
// through this stub keeps these tests independent of intent-classification —
// which needs a live Anthropic key this environment doesn't have — while
// still exercising the real Speaking Service WebSocket, the real
// AudioRecorder, and the real waveform-canvas/useAudioVisualizer code below
// it. That's a deliberate boundary, not a shortcut: classification is a
// separate LLM-routing concern from "does the speaking session actually
// work once the frontend is told where to connect," which is what this file
// tests.
async function mockSpeakingUrl(page: Page) {
  await page.route("**/api/chat", async (route) => {
    const sse =
      `event: metadata\n` +
      `data: ${JSON.stringify({ type: "metadata", intent: "SPEAKING", confidence: 0.99 })}\n\n` +
      `event: speaking_url\n` +
      `data: ${JSON.stringify({ type: "speaking_url", wsUrl: "ws://localhost:8080/api/speaking/ws" })}\n\n`;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse,
    });
  });
}

async function isSpeakingServiceReachable(
  request: import("@playwright/test").APIRequestContext,
): Promise<boolean> {
  const speakingServiceURL =
    process.env.SPEAKING_SERVICE_URL ?? "http://localhost:8082";
  return request
    .get(`${speakingServiceURL}/metrics`, { timeout: 2000 })
    .then((res) => res.ok())
    .catch(() => false);
}

test.describe("GOA Speaking Practice", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
  });

  test("opens speaking practice panel", async ({ page }) => {
    await page.getByTitle("Speaking Practice").click();

    await expect(page.getByTestId("speaking-panel")).toBeVisible();
  });

  test("starts microphone session", async ({ page }) => {
    await page.context().grantPermissions(["microphone"]);

    await page.getByTitle("Speaking Practice").click();

    await page.getByTestId("start-speaking-button").click();

    await expect(page.getByTestId("live-transcript")).toBeVisible();
  });

  test("shows the start button when the panel opens", async ({ page }) => {
    await page.goto("/chat");

    await page.getByTitle("Speaking Practice").click();

    await expect(page.getByTestId("start-speaking-button")).toBeVisible();
  });

  // Requires the Speaking Service (not the full orchestration+LLM stack —
  // see mockSpeakingUrl above) to be reachable, since it exercises a real
  // WebSocket handshake. Skips rather than fails when it isn't, so the
  // default `npm run test:e2e` run stays green on a frontend-only checkout.
  test("does not claim 'Listening' until the WebSocket actually connects", async ({
    page,
    request,
  }) => {
    test.skip(
      !(await isSpeakingServiceReachable(request)),
      "Speaking service not reachable — this test needs a live WebSocket handshake.",
    );

    await mockSpeakingUrl(page);
    await page.context().grantPermissions(["microphone"]);

    await page.getByTitle("Speaking Practice").click();
    await page.getByTestId("start-speaking-button").click();

    // Immediately after the click — before any network round trip can
    // possibly have completed — the UI must not already claim "Listening".
    // Regression guard for the bug where startSpeaking() set this
    // synchronously on click, before a WebSocket even existed.
    await expect(page.getByText(/^Status:/)).not.toHaveText(/listening/i);

    // ...but it must still reach "listening" once the real handshake
    // completes, rather than getting stuck on "connecting" forever.
    await expect(page.getByText(/^Status:/)).toHaveText(/listening/i, {
      timeout: 15000,
    });
  });

  test("renders the waveform canvas once a speaking session is actually connected", async ({
    page,
    request,
  }) => {
    test.skip(
      !(await isSpeakingServiceReachable(request)),
      "Speaking service not reachable — the waveform only appears once a live WebSocket delivers a MediaStream.",
    );

    await mockSpeakingUrl(page);
    await page.context().grantPermissions(["microphone"]);

    await page.getByTitle("Speaking Practice").click();
    await page.getByTestId("start-speaking-button").click();

    const canvas = page.getByTestId("waveform-canvas");
    await expect(canvas).toBeVisible({ timeout: 15000 });
    await expect(canvas).toHaveAttribute("aria-hidden", "true");
  });

  test("animates the waveform with non-zero pixel data while recording", async ({
    page,
    request,
  }) => {
    test.skip(
      !(await isSpeakingServiceReachable(request)),
      "Speaking service not reachable — this test needs the real recording pipeline.",
    );

    await mockSpeakingUrl(page);
    await page.context().grantPermissions(["microphone"]);

    await page.getByTitle("Speaking Practice").click();
    await page.getByTestId("start-speaking-button").click();

    const canvas = page.getByTestId("waveform-canvas");
    await expect(canvas).toBeVisible({ timeout: 15000 });

    const countNonZeroPixels = () =>
      canvas.evaluate((el: HTMLCanvasElement) => {
        const ctx = el.getContext("2d");
        if (!ctx || el.width === 0 || el.height === 0) return 0;

        const { data } = ctx.getImageData(0, 0, el.width, el.height);
        let nonZero = 0;
        for (let i = 3; i < data.length; i += 4) {
          if (data[i] !== 0) nonZero++;
        }
        return nonZero;
      });

    // Canvas contains non-zero pixel values once the analyser starts drawing.
    await expect.poll(countNonZeroPixels, { timeout: 10000 }).toBeGreaterThan(0);

    // And it's genuinely animating frame to frame, not just drawn once.
    // Chromium's fake audio capture device emits its synthetic tone in
    // periodic bursts rather than continuously, so a single short two-frame
    // diff can land entirely inside a silent gap between bursts (this was
    // observed directly while validating this fix). Sampling repeatedly
    // across a few seconds makes the assertion robust to that instead of
    // just picking a longer arbitrary gap and hoping.
    const frames: string[] = [];
    for (let i = 0; i < 15; i++) {
      frames.push(
        await canvas.evaluate((el: HTMLCanvasElement) => el.toDataURL()),
      );
      await page.waitForTimeout(200);
    }
    expect(new Set(frames).size).toBeGreaterThan(1);
  });
});

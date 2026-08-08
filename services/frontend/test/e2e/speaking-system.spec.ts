import { test, expect } from "./fixtures/auth";

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

// Phase D (docs/IA-REDESIGN-PROPOSAL.md): Speaking Practice moved out of Chat
// onto its own page, /practice/speaking. The panel there is always mounted
// (no toolbar button needed to open it first, unlike the old chat-embedded
// version) -- these tests go straight to the page and interact with the
// panel directly. The mockSpeakingUrl helper these tests used to share
// mocked /api/chat's speaking_url SSE event, but the button-driven flow this
// file actually exercises (Start -> direct WebSocket) never went through
// /api/chat even before this move, so nothing here depended on that mock in
// the first place.
test.describe("Dalil Speaking Practice", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/practice/speaking");
  });

  test("shows the speaking panel on load", async ({ page }) => {
    await expect(page.getByTestId("speaking-panel")).toBeVisible();
  });

  test("shows the start button on load", async ({ page }) => {
    await expect(page.getByTestId("start-speaking-button")).toBeVisible();
  });

  test("starts microphone session", async ({ page }) => {
    await page.context().grantPermissions(["microphone"]);

    await page.getByTestId("start-speaking-button").click();

    await expect(page.getByTestId("live-transcript")).toBeVisible();
  });

  // Requires the Speaking Service to be reachable, since it exercises a real
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

    await page.context().grantPermissions(["microphone"]);

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

    await page.context().grantPermissions(["microphone"]);

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

    await page.context().grantPermissions(["microphone"]);

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

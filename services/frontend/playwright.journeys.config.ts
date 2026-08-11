import { defineConfig, devices } from "@playwright/test";

/**
 * GOA-030 — the live-stack journey suite.
 *
 * Separate from playwright.config.ts on purpose. That config owns test/e2e/,
 * which is a mocked UI contract suite: it runs with no backend, seeds a
 * placeholder cookie, and is fast enough to be a per-commit gate. This one owns
 * test/journeys/, which needs the whole docker-compose stack, a real LLM
 * budget and minutes rather than seconds. Merging them would mean either
 * running the mocked suite against a stack it does not need, or gating commits
 * on a suite that cannot run in CI.
 *
 * Run:
 *   docker compose up -d
 *   npx playwright test -c playwright.journeys.config.ts
 */

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const useExternalBaseURL = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
  testDir: "./test/journeys",

  // The AC asks for 4 workers. One worker per journey is also what keeps the
  // 60-requests-per-user-per-minute Gateway limit survivable: the journeys hold
  // separate accounts, so the budget is per journey rather than shared.
  workers: 4,
  fullyParallel: false,

  // A journey is a sequence of real model calls. Essay evaluation alone was
  // measured at ~52s against AgentRouter and the Gateway allows it 6 minutes,
  // so a per-test budget in the default 30s is not a timeout, it is a
  // guaranteed failure.
  timeout: 10 * 60 * 1000,
  expect: { timeout: 30 * 1000 },

  // Zero retries, deliberately. A retry here re-runs real model calls at real
  // cost, and worse: a journey that only passes on the second attempt is
  // telling you something true about the product that a green retry hides.
  retries: 0,

  reporter: [
    ["list"],
    // Produces summary.json, collects screenshots and traces, pushes
    // goa_e2e_step_duration_ms, and uploads the run to S3.
    ["./test/journeys/fixtures/reporter.ts"],
  ],

  use: {
    baseURL,
    // The AC wants a trace on any failure, containing network requests, DOM
    // snapshots and console logs -- which is exactly what a Playwright trace
    // is, so nothing else has to be assembled by hand.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Journeys wait on real model calls; the default 30s action timeout fires
    // mid-stream and reports a product failure that is really a test budget.
    actionTimeout: 60 * 1000,
    navigationTimeout: 60 * 1000,
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--mute-audio",
      ],
    },
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  // Built and served rather than `next dev`, for the reason the sibling config
  // documents at length: under parallel workers the first request to an
  // uncompiled route returns a 404 while Next is still building it, and the
  // 2026-08-09 audit recorded 56 failures from exactly that against a build
  // where all 30 routes compiled.
  webServer: useExternalBaseURL
    ? undefined
    : {
        command: "npm run build && npm run start",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 600 * 1000,
        env: { NEXT_PUBLIC_BILLING_ENABLED: "true" },
      },
});

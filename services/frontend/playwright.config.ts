import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000";
const useExternalBaseURL = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
  // Scoped to test/e2e so Playwright's default *.test.ts matcher doesn't
  // also try to collect the Vitest unit tests under lib/ (e.g.
  // lib/reading-grading.test.ts), which fail under Playwright's runner
  // since they import from "vitest".
  testDir: "./test/e2e",

  /* Set the base URL so relative paths work across all tests */
  use: {
    baseURL,
    trace: "on-first-retry",

    /* Bypasses hardware mic prompts by feeding fake audio devices into the browser context */
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        "--mute-audio",
      ],
    },
  },

  /* Run tests across major desktop engines */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Start Next before the suite, unless a server is already supplied.
   *
   * `npm run dev` compiles a route the first time it is requested. Under
   * parallel workers the first hit on an uncompiled route returns a 404 while
   * Next is still building it, and the run reports dozens of "missing" routes
   * that a production build proves are present -- the 2026-08-09 audit saw 56
   * failures this way against a build where all 30 routes compiled.
   *
   * So the suite builds and serves by default: `next start` has every route
   * ready before the first request, which is also closer to what ships.
   *
   * E2E_DEV_SERVER=true opts back into the dev server for local iteration,
   * where hot reload is worth more than parallel stability. Use one worker
   * with it.
   */
  webServer: useExternalBaseURL
    ? undefined
    : {
        command: process.env.E2E_DEV_SERVER === "true"
          ? "npm run dev"
          : "npm run build && npm run start",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        // A production build is slower to start than a dev server and this
        // budget covers the build itself, not just the boot.
        timeout: (process.env.E2E_DEV_SERVER === "true" ? 120 : 600) * 1000,
        env: {
          // GOA-039. The billing flag is off by default because the Gateway
          // does not serve /api/billing/* yet; the upgrade specs mock those
          // routes with page.route, so the UI has to offer the action for
          // them to have anything to intercept.
          NEXT_PUBLIC_BILLING_ENABLED: "true",
        },
      },
});


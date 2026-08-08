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

  /* Automatically start Next.js dev server before running tests if not running */
  webServer: useExternalBaseURL
    ? undefined
    : {
        command: "npm run dev",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
        env: {
          // GOA-039. The billing flag is off by default because the Gateway
          // does not serve /api/billing/* yet; the upgrade specs mock those
          // routes with page.route, so the UI has to offer the action for
          // them to have anything to intercept.
          NEXT_PUBLIC_BILLING_ENABLED: "true",
        },
      },
});


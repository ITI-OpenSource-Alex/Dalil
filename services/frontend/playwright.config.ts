import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  /* Set the base URL so relative paths work across all tests */
  use: {
    baseURL: "http://localhost:3000",
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
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  },
});


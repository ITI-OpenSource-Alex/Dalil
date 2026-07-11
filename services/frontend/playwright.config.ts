import { defineConfig } from "@playwright/test";

export default defineConfig({
  use: {
    /* Set the base URL so relative paths like page.goto('/exam') work */
    baseURL: "http://localhost:3000",
  },

  /* Automatically start Next.js dev server before running tests if not running */
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});

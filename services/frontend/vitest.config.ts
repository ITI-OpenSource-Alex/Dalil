import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Keep Playwright's own spec files out of Vitest's discovery — both
    // tools default to picking up *.test.ts/*.spec.ts otherwise.
    exclude: ["**/node_modules/**", "**/e2e/**", "**/*.spec.ts"],
  },
  resolve: {
    alias: {
      // Matches tsconfig.json: "@/*": ["./*"]
      "@": path.resolve(__dirname, "./"),
    },
  },
});

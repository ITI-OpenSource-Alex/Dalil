import { defineConfig } from "vitest/config";
import path from "path";

// Minimal config: GOA-055's Definition of Done requires unit tests for pure
// logic (fill-blank comparison, breakdown percentage calculation) — no unit
// test runner existed in this repo before this ticket. Scoped to just what
// those tests need (plain TS, no DOM/jsdom, no component rendering).
export default defineConfig({
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});

import type { NextConfig } from "next";
import path from "path";
import { fileURLToPath } from "url";

// Pin Turbopack's root to this package. Without it, Next walks up to
// G:\ITImaterial\package-lock.json and treats that as the workspace root,
// which has produced corrupted .next/dev/types/validator.ts output during
// e2e webServer boots (truncated route paths like "ing/history/[id]").
const packageRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    root: packageRoot,
  },
};

export default nextConfig;

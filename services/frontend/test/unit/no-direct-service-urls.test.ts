import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * GOA-132 regression guard, as a test rather than a checklist item.
 *
 * Every browser-facing call goes through the Gateway. A direct service port in
 * client code means that call skips JWT validation, rate limiting and
 * correlation IDs — which is exactly how BUG-029 and BUG-046 happened, and how
 * Speaking's session routes ended up reading `userId` from a query string the
 * caller controlled.
 *
 * Scoped to client code on purpose: test harnesses and Playwright fixtures may
 * legitimately talk to a service directly to set up or assert state.
 */
const ROOT = join(__dirname, "..", "..");
const CLIENT_DIRS = ["app", "lib", "components"];
const FORBIDDEN = [
  { pattern: /localhost:8082/, service: "speaking", route: "/api/speaking/*" },
  { pattern: /localhost:8084/, service: "rag", route: "/api/opportunities/query" },
  { pattern: /localhost:8085/, service: "exam", route: "/api/exam/*" },
  { pattern: /NEXT_PUBLIC_SPEAKING_API_URL/, service: "speaking", route: "/api/speaking/*" },
  { pattern: /NEXT_PUBLIC_INTERNAL_API_KEY/, service: "any", route: "the Gateway (the key must never reach the browser)" },
];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (current: string) => {
    for (const entry of readdirSync(current)) {
      if (entry === "node_modules" || entry.startsWith(".")) continue;
      const full = join(current, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry)) {
        out.push(full);
      }
    }
  };
  walk(join(ROOT, dir));
  return out;
}

describe("no direct service URLs in client code", () => {
  const files = CLIENT_DIRS.flatMap(sourceFiles);

  it("finds client source files to scan", () => {
    // Without this, a broken path would make the suite below vacuously pass.
    expect(files.length).toBeGreaterThan(20);
  });

  for (const { pattern, service, route } of FORBIDDEN) {
    it(`no client code references ${pattern.source} (use ${route})`, () => {
      const offenders = files
        .map((file) => ({ file, source: readFileSync(file, "utf8") }))
        .flatMap(({ file, source }) =>
          source
            .split("\n")
            .map((line, index) => ({ file, line, number: index + 1 }))
            // Comments explaining why the old URL is gone are the point, not a
            // violation.
            .filter(({ line }) => pattern.test(line) && !/^\s*(\/\/|\*|\/\*)/.test(line)),
        )
        .map(({ file, number, line }) => `${relative(ROOT, file)}:${number}: ${line.trim()}`);

      expect(
        offenders,
        `client code must reach ${service} through the Gateway at ${route}`,
      ).toEqual([]);
    });
  }
});

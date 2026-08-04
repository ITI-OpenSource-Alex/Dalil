import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Guards the server/client boundary of the design system.
 *
 * A primitive that gains a "use client" directive drags every page importing
 * it across the boundary. For the marketing pages -- which are entirely
 * server-rendered and are the product's highest-traffic surface -- that turns
 * a static page into a hydrated one. The regression is invisible in review
 * and invisible at runtime, so it is asserted here instead.
 *
 * Moving a component between these lists is a deliberate architectural
 * decision. Changing the list is fine; changing it by accident is not.
 */

const UI_DIR = join(process.cwd(), "components/ui");

const MUST_BE_SERVER_RENDERABLE = [
  "button.tsx",
  "card.tsx",
  "badge.tsx",
  "alert.tsx",
  "heading.tsx",
  "text.tsx",
  "icon.tsx",
  "spinner.tsx",
  "skeleton.tsx",
  "progress.tsx",
  "empty-state.tsx",
  "page-container.tsx",
];

const CLIENT_BY_DESIGN = [
  "field.tsx", // useId
  "input.tsx", // consumes Field context
  "checkbox.tsx", // useRef/useEffect for indeterminate
  "radio.tsx",
  "switch.tsx",
  "modal.tsx", // Radix
  "tabs.tsx", // Radix
  "tooltip.tsx", // Radix
  // Phase 4: app chrome, not a marketing-page primitive, but it does hold
  // its own state (mobile drawer, user menu) and fetches identity.
  "sidebar.tsx",
];

function read(file: string) {
  return readFileSync(join(UI_DIR, file), "utf8");
}

describe("UI primitive server/client boundary", () => {
  it.each(MUST_BE_SERVER_RENDERABLE)(
    "%s is server-renderable (no 'use client')",
    (file) => {
      expect(read(file)).not.toMatch(/^\s*["']use client["']/m);
    },
  );

  it.each(MUST_BE_SERVER_RENDERABLE)(
    "%s does not import a client-only primitive",
    (file) => {
      const source = read(file);
      const imports = [...source.matchAll(/from\s+["']\.\/([\w-]+)["']/g)].map(
        (m) => `${m[1]}.tsx`,
      );
      const leaked = imports.filter((i) => CLIENT_BY_DESIGN.includes(i));
      expect(leaked).toEqual([]);
    },
  );

  it.each(CLIENT_BY_DESIGN)("%s declares 'use client'", (file) => {
    expect(read(file)).toMatch(/^\s*["']use client["']/m);
  });

  it("covers every primitive in the directory", () => {
    const actual = readdirSync(UI_DIR).filter(
      (f) => f.endsWith(".tsx") && !f.endsWith(".test.tsx"),
    );
    const covered = [...MUST_BE_SERVER_RENDERABLE, ...CLIENT_BY_DESIGN];
    const uncovered = actual.filter((f) => !covered.includes(f));
    expect(uncovered).toEqual([]);
  });
});

describe("design token discipline", () => {
  const sources = readdirSync(UI_DIR)
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => ({ file: f, source: read(f) }));

  it.each(sources.map((s) => s.file))(
    "%s uses no raw hex colours",
    (file) => {
      const source = sources.find((s) => s.file === file)!.source;
      // Strip comments, which legitimately quote hex values when explaining
      // what a token replaced.
      const code = source
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/\/\/.*$/gm, "");
      expect(code.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).toEqual([]);
    },
  );

  it.each(sources.map((s) => s.file))(
    "%s uses no default Tailwind neutral ramps",
    (file) => {
      const source = sources.find((s) => s.file === file)!.source;
      const code = source
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/\/\/.*$/gm, "");
      // sage-* is the project's own neutral and is allowed; gray/slate/zinc/
      // neutral/stone are Tailwind defaults and are what the migration retires.
      const hits =
        code.match(
          /\b(?:bg|text|border|ring|from|via|to|fill|stroke)-(?:gray|slate|zinc|neutral|stone)-\d{2,3}\b/g,
        ) ?? [];
      expect(hits).toEqual([]);
    },
  );
});

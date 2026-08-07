import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge ships knowing Tailwind's default scales, but not the
// semantic ones added in globals.css. Without teaching it, `rounded-card`
// and `shadow-e2` are treated as unrelated to `rounded-lg`/`shadow-sm`, so a
// caller passing `rounded-card` to a component whose base is `rounded-control`
// would end up with both classes and the losing one decided by stylesheet
// order rather than by the prop.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-family": [{ font: ["sans", "serif", "mono"] }],
      rounded: [{ rounded: ["chip", "control", "card", "panel"] }],
      shadow: [{ shadow: ["e1", "e2", "e3", "e4"] }],
    },
  },
});

/**
 * Merges Tailwind classes so that a caller-supplied `className` always wins
 * over a component's own defaults, instead of silently colliding.
 *
 * The single approved way to compose classes. Components take a `className`
 * prop, pass it last, and never concatenate with template strings -- which
 * is what the codebase does today and why overriding a variant currently
 * depends on which utility Tailwind happened to emit first.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

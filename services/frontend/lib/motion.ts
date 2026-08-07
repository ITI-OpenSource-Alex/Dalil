/**
 * Shared motion vocabulary: durations and easings, mirroring the
 * --duration and --ease custom properties in globals.css so framer-motion
 * literals (which take seconds) and CSS transitions (which take
 * milliseconds) stay expressed in the same terms.
 *
 * This previously also exported a set of framer-motion `Variants` presets
 * (fadeIn/fadeUp/scaleIn/slideInRight/stagger/reduced/inViewOnce) meant to be
 * the one shared vocabulary every animated component pulls from. In practice
 * every animated component (chat, dashboard, marketing) still writes its own
 * inline `initial`/`animate`/`transition` literals instead, so those presets
 * had no call sites — removed rather than left as unused, never-adopted API.
 */

export const DURATION = {
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
  slower: 0.5,
} as const;

/** Matches --ease-* in globals.css. */
export const EASE = {
  /** House curve: fast start, long settle. Default for enter transitions. */
  out: [0.16, 1, 0.3, 1],
  inOut: [0.65, 0, 0.35, 1],
  spring: [0.34, 1.56, 0.64, 1],
} as const;

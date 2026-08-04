import type { Transition, Variants } from "framer-motion";

/**
 * Shared motion vocabulary.
 *
 * Every animated component pulls its durations, easings and variants from
 * here. Before this existed, framer-motion literals like `duration: 0.4,
 * delay: 0.15` were written inline in fifteen files with no shared meaning,
 * and CSS transitions were almost all a bare `transition` class -- which
 * animates *every* property, including layout ones, at the browser default.
 *
 * Durations mirror the --duration-* custom properties in globals.css.
 * framer-motion takes seconds; CSS takes milliseconds.
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

export const transitions = {
  fast: { duration: DURATION.fast, ease: EASE.out },
  base: { duration: DURATION.base, ease: EASE.out },
  slow: { duration: DURATION.slow, ease: EASE.out },
} satisfies Record<string, Transition>;

/* ------------------------------------------------------------------ *
 * Variants
 *
 * Each is a plain object so a component can spread and extend it. Use
 * `reduced()` below rather than these directly wherever the animation
 * involves movement.
 * ------------------------------------------------------------------ */

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transitions.base },
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: transitions.slow },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition: transitions.base },
};

export const slideInRight: Variants = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0, transition: transitions.base },
  exit: { opacity: 0, x: 24, transition: transitions.fast },
};

/**
 * Staggers children by 60ms. Apply to a parent with `variants={stagger()}`
 * and give each child `variants={fadeUp}`.
 */
export function stagger(staggerChildren = 0.06, delayChildren = 0): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren, delayChildren } },
  };
}

/**
 * Strips movement from a variant set when the user has asked for reduced
 * motion, leaving the opacity change intact so the element still reads as
 * "arriving" rather than snapping in.
 *
 * Pair with framer-motion's useReducedMotion():
 *
 *   const reduce = useReducedMotion();
 *   <motion.div variants={reduced(fadeUp, reduce)} />
 *
 * The global CSS kill switch in globals.css covers CSS transitions, but
 * framer-motion animates via inline style and is not affected by it -- this
 * is the other half of honouring the preference.
 */
export function reduced(variants: Variants, prefersReduced: boolean | null): Variants {
  if (!prefersReduced) return variants;
  return fadeIn;
}

/** Standard `whileInView` config for marketing scroll reveals: once only. */
export const inViewOnce = {
  initial: "hidden",
  whileInView: "visible",
  viewport: { once: true, amount: 0.25 },
} as const;

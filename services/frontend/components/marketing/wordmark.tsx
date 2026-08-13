import { cn } from "@/lib/cn";

/**
 * The Dalil lockup: the monogram followed by the wordmark, served from the
 * official logo artwork in public/.
 *
 * The artwork is loaded as a file rather than inlined, so public/logo.svg is
 * the single source of truth for the brand — the same asset the OG card and
 * the favicon are cut from. Two variants exist because the mark is a
 * two-colour drawing (forest ink + teal), not a single-path glyph that could
 * be recoloured with currentColor: `logo.svg` for light surfaces, and
 * `logo-light.svg`, identical geometry with the ink swapped to sage-50, for
 * the dark navbar / footer / auth panel.
 *
 * This one component backs marketing, the authenticated shell and onboarding,
 * so the brand does not change identity when a user signs in.
 */

const LOGO_SRC = {
  default: "/logo.svg",
  inverse: "/logo-light.svg",
} as const;

/* Intrinsic size of the artwork (both variants share a viewBox). Passed to
   the <img> so the browser reserves the right box before the SVG loads —
   without it the header reflows on first paint. */
const LOGO_WIDTH = 1159;
const LOGO_HEIGHT = 293;

export interface WordmarkProps {
  tone?: "default" | "inverse";
  /**
   * Merged onto the <img> itself, so a caller can override the default `h-8`
   * with its own height and the width still follows from the aspect ratio.
   */
  className?: string;
}

export function Wordmark({ tone = "default", className }: WordmarkProps) {
  return (
    <span className="inline-flex items-center">
      {/* eslint-disable-next-line @next/next/no-img-element -- a static SVG
          has nothing for next/image to optimise, and routing it through the
          optimiser would require dangerouslyAllowSVG. */}
      <img
        src={LOGO_SRC[tone]}
        alt=""
        aria-hidden="true"
        width={LOGO_WIDTH}
        height={LOGO_HEIGHT}
        // max-w-full so a narrow phone header shrinks the lockup rather than
        // letting it overflow the bar.
        className={cn("h-8 w-auto max-w-full", className)}
      />
      {/* The name is carried as text rather than as an aria-label on the
          wrapping link: see the note in navbar.tsx on why overriding the
          accessible name of a link trips label-content-name-mismatch. */}
      <span className="sr-only">Dalil</span>
    </span>
  );
}

import { cn } from "@/lib/cn";

/**
 * Heading sizes, decoupled from heading LEVEL.
 *
 * `as` controls semantics (document outline, screen-reader navigation);
 * `size` controls appearance. Keeping them separate is what lets a page have
 * exactly one <h1> without being forced into one particular size, and stops
 * the common hack of picking <h3> because <h2> "looked too big".
 *
 * Serif is applied only at display sizes (lg and up). This app has several
 * headings that are 14px section labels -- profile's "Account", the writing
 * panel's group titles -- where a serif reads as a mistake rather than as a
 * voice. Encoding that in the scale means it cannot be got wrong per call site.
 */
export type HeadingSize = "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl";

const SIZE: Record<HeadingSize, string> = {
  /* --- Sans. UI labels and card titles. ------------------------------- */
  // Section label. Small, uppercase-adjacent, used above a group of fields.
  xs: "font-sans text-sm font-semibold tracking-normal",
  sm: "font-sans text-base font-semibold tracking-normal",
  md: "font-sans text-xl font-semibold tracking-tight",

  /* --- Serif. Display sizes only. ------------------------------------- */
  // Subsection headings inside a page.
  lg: "font-serif text-2xl font-semibold tracking-tight",
  // Page titles in the authenticated app.
  xl: "font-serif text-3xl font-semibold tracking-tight lg:text-4xl",
  // Marketing section headings.
  "2xl": "font-serif text-4xl font-semibold tracking-tight lg:text-5xl",
  // Hero only. There should be at most one of these per page.
  "3xl": "font-serif text-5xl font-bold tracking-tight lg:text-7xl",
};

// Display type needs a tighter leading than body copy; at 72px the default
// 1.5 line-height opens gaps you could park a car in.
const LEADING: Record<HeadingSize, string> = {
  xs: "leading-snug",
  sm: "leading-snug",
  md: "leading-snug",
  lg: "leading-snug",
  xl: "leading-tight",
  "2xl": "leading-tight",
  "3xl": "leading-[1.05]",
};

export interface HeadingProps
  extends React.HTMLAttributes<HTMLHeadingElement> {
  /** Semantic level. Choose for document structure, never for size. */
  as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
  size?: HeadingSize;
  /** Muted tone for secondary headings that shouldn't compete. */
  tone?: "default" | "muted" | "inverse";
  /**
   * Balances the final line so headings don't end on a single orphaned word.
   * On by default: it is the cheapest typographic upgrade available and is
   * ignored by browsers that don't support it.
   */
  balance?: boolean;
}

const TONE = {
  default: "text-fg",
  muted: "text-fg-muted",
  inverse: "text-fg-inverse",
} as const;

export function Heading({
  as: Component = "h2",
  size = "lg",
  tone = "default",
  balance = true,
  className,
  children,
  ...props
}: HeadingProps) {
  return (
    <Component
      className={cn(
        SIZE[size],
        LEADING[size],
        TONE[tone],
        balance && "text-balance",
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  );
}

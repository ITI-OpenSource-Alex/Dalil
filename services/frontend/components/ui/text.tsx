import { cn } from "@/lib/cn";

/**
 * Body copy.
 *
 * The default size is `base` (16px), not `sm`. The audit found text-sm and
 * text-xs accounting for 294 of ~370 sizing declarations against 7 uses of
 * text-base -- the app was almost entirely 12-14px, which is the main reason
 * it read as dense and unfinished. Making 16px the path of least resistance
 * is the point of this component.
 *
 * `xs` is for metadata and badges. It is not a body size.
 */
export type TextSize = "xs" | "sm" | "base" | "lg";
export type TextTone =
  | "default"
  | "muted"
  | "subtle"
  | "brand"
  | "danger"
  | "success"
  | "warning"
  | "inverse"
  | "inverse-muted";

const SIZE: Record<TextSize, string> = {
  xs: "text-xs leading-5",
  sm: "text-sm leading-6",
  // Generous leading: this is reading copy, not a label.
  base: "text-base leading-7",
  lg: "text-lg leading-8",
};

const TONE: Record<TextTone, string> = {
  default: "text-fg",
  muted: "text-fg-muted",
  subtle: "text-fg-subtle",
  brand: "text-brand-fg",
  danger: "text-danger-fg",
  success: "text-success-fg",
  warning: "text-warning-fg",
  inverse: "text-fg-inverse",
  "inverse-muted": "text-fg-inverse-muted",
};

const WEIGHT = {
  normal: "font-normal",
  medium: "font-medium",
  semibold: "font-semibold",
} as const;

export interface TextProps extends React.HTMLAttributes<HTMLElement> {
  /** `p` for paragraphs, `span` inline, `div` when wrapping block content. */
  as?: "p" | "span" | "div" | "dd" | "dt" | "li" | "label";
  size?: TextSize;
  tone?: TextTone;
  weight?: keyof typeof WEIGHT;
  /**
   * Caps line length for readability. Prose beyond ~75 characters per line is
   * measurably harder to scan; long descriptions on wide screens are one of
   * the landing page's current readability problems.
   */
  measure?: boolean;
  /** Truncates to a single line with an ellipsis. */
  truncate?: boolean;
  /** Clamps to N lines. Useful in cards where content length varies. */
  clamp?: 2 | 3 | 4;
}

const CLAMP = {
  2: "line-clamp-2",
  3: "line-clamp-3",
  4: "line-clamp-4",
} as const;

export function Text({
  as: Component = "p",
  size = "base",
  tone = "default",
  weight = "normal",
  measure = false,
  truncate = false,
  clamp,
  className,
  children,
  ...props
}: TextProps) {
  return (
    <Component
      className={cn(
        SIZE[size],
        TONE[tone],
        WEIGHT[weight],
        measure && "max-w-[68ch]",
        truncate && "truncate",
        clamp && CLAMP[clamp],
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  );
}

/**
 * Small uppercase label that sits above a heading. Used for the eyebrow line
 * in marketing sections and as a group label in dense app UI.
 */
export function Eyebrow({
  tone = "brand",
  className,
  children,
  ...props
}: Omit<TextProps, "size" | "weight">) {
  return (
    <Text
      as="span"
      size="xs"
      tone={tone}
      weight="semibold"
      className={cn("uppercase tracking-[0.08em]", className)}
      {...props}
    >
      {children}
    </Text>
  );
}

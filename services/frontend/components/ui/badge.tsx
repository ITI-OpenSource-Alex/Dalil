import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";

/* Unifies the pill chips currently hand-written in at least six places:
   pricing's "Most popular", the sidebar's "Soon", profile's "Your Profile",
   the hero eyebrow, speaking's status chips and the landing section labels —
   each with different padding, radius and colour. */

export type BadgeTone =
  | "neutral"
  | "brand"
  | "accent"
  | "success"
  | "warning"
  | "danger"
  | "info";

export type BadgeVariant = "subtle" | "solid" | "outline";

const TONE: Record<BadgeTone, Record<BadgeVariant, string>> = {
  neutral: {
    subtle: "bg-canvas-inset text-fg-muted",
    solid: "bg-fg-muted text-white",
    outline: "border border-border-strong text-fg-muted",
  },
  brand: {
    subtle: "bg-brand-muted text-brand-fg",
    solid: "bg-brand text-fg-on-brand",
    outline: "border border-brand-border text-brand-fg",
  },
  accent: {
    subtle: "bg-accent-subtle text-accent-fg",
    solid: "bg-accent text-fg-on-accent",
    outline: "border border-accent-border text-accent-fg",
  },
  success: {
    subtle: "bg-success-subtle text-success-fg",
    solid: "bg-success text-white",
    outline: "border border-success-border text-success-fg",
  },
  warning: {
    subtle: "bg-warning-subtle text-warning-fg",
    solid: "bg-warning text-white",
    outline: "border border-warning-border text-warning-fg",
  },
  danger: {
    subtle: "bg-danger-subtle text-danger-fg",
    solid: "bg-danger text-white",
    outline: "border border-danger-border text-danger-fg",
  },
  info: {
    subtle: "bg-info-subtle text-info-fg",
    solid: "bg-info text-white",
    outline: "border border-info-border text-info-fg",
  },
};

const SIZE = {
  sm: "h-5 gap-1 px-2 text-xs",
  md: "h-6 gap-1.5 px-2.5 text-xs",
  lg: "h-7 gap-1.5 px-3 text-sm",
} as const;

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  variant?: BadgeVariant;
  size?: keyof typeof SIZE;
  icon?: LucideIcon;
  /**
   * Shows a filled dot before the label. For status that is a *state* rather
   * than a category — "Live", "Recording", "Draft".
   */
  dot?: boolean;
  /** Pill shape. Default is the chip radius. */
  pill?: boolean;
  /**
   * Announces the badge as a live status region. Use only for text that
   * changes in place, such as a recording timer or connection state.
   */
  live?: boolean;
}

export function Badge({
  tone = "neutral",
  variant = "subtle",
  size = "md",
  icon,
  dot = false,
  pill = false,
  live = false,
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      role={live ? "status" : undefined}
      aria-live={live ? "polite" : undefined}
      className={cn(
        "inline-flex items-center font-medium whitespace-nowrap",
        pill ? "rounded-full" : "rounded-chip",
        TONE[tone][variant],
        SIZE[size],
        className,
      )}
      {...props}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-current"
        />
      )}
      {icon && <Icon icon={icon} size="xs" />}
      {children}
    </span>
  );
}

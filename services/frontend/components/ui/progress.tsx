import React from "react";
import { cn } from "@/lib/cn";

/**
 * Determinate progress bar.
 *
 * A div with role="progressbar" rather than <progress>, because <progress>
 * cannot be styled consistently across browsers without vendor hacks, while
 * the ARIA role carries exactly the same semantics.
 *
 * Replaces the hand-rolled track/fill pair in the onboarding wizard and the
 * checklist progress meter, neither of which currently exposes its value to
 * assistive technology at all.
 */

const TONE = {
  brand: "bg-brand",
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
} as const;

const SIZE = {
  sm: "h-1",
  md: "h-2",
  lg: "h-3",
} as const;

export interface ProgressProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "children"> {
  /** Current value, clamped to [0, max]. */
  value: number;
  max?: number;
  tone?: keyof typeof TONE;
  size?: keyof typeof SIZE;
  /**
   * Accessible name. Required — a progress bar with no name announces only a
   * percentage, which tells a screen-reader user nothing about what is
   * progressing.
   */
  label: string;
  /**
   * Human-readable form of the current value, e.g. "Step 2 of 4". Announced
   * in place of the raw percentage when supplied.
   */
  valueText?: string;
  /** Renders the label and value above the track. */
  showValue?: boolean;
}

export function Progress({
  value,
  max = 100,
  tone = "brand",
  size = "md",
  label,
  valueText,
  showValue = false,
  className,
  ...props
}: ProgressProps) {
  const safeMax = max > 0 ? max : 100;
  const clamped = Math.min(Math.max(value, 0), safeMax);
  const percent = (clamped / safeMax) * 100;

  return (
    <div className={cn("flex flex-col gap-2", className)} {...props}>
      {showValue && (
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-sm font-medium text-fg">{label}</span>
          <span className="text-sm tabular-nums text-fg-subtle">
            {valueText ?? `${Math.round(percent)}%`}
          </span>
        </div>
      )}

      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={safeMax}
        aria-valuetext={valueText}
        aria-label={showValue ? undefined : label}
        className={cn(
          "w-full overflow-hidden rounded-full bg-canvas-inset",
          SIZE[size],
        )}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-320 ease-out",
            TONE[tone],
          )}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

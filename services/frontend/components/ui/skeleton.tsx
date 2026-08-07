import React from "react";
import { cn } from "@/lib/cn";

/**
 * Loading placeholder.
 *
 * A shimmer rather than a pulse: a sweeping highlight reads as "content is
 * arriving", where a fading block reads as "something is broken". Under
 * prefers-reduced-motion the global rule in globals.css stops the sweep,
 * leaving a static block that still communicates the right thing.
 *
 * The previous version used bg-gray-200 — one of the last hardcoded neutrals.
 * The default output (h-4 w-full, single line) is unchanged, so the existing
 * callers in profile/page.tsx and exam/results/page.tsx keep their layout.
 */

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Matches the shape of whatever is loading. */
  shape?: "text" | "block" | "circle";
  /** For shape="text": renders N stacked lines, the last one short. */
  lines?: number;
}

const SHIMMER =
  "bg-canvas-inset bg-[linear-gradient(90deg,transparent_0%,var(--color-surface)_50%,transparent_100%)] bg-[length:200%_100%] animate-shimmer";

export function Skeleton({
  shape = "text",
  lines = 1,
  className,
  ...props
}: SkeletonProps) {
  if (shape === "text" && lines > 1) {
    return (
      <div className={cn("flex flex-col gap-2", className)} {...props}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={cn(
              SHIMMER,
              "h-4 rounded-chip",
              // A block of equal-length lines reads as a table, not as prose.
              // Shortening the last line is what makes it read as a paragraph.
              i === lines - 1 ? "w-3/5" : "w-full",
            )}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        SHIMMER,
        shape === "circle" && "aspect-square rounded-full",
        shape === "block" && "rounded-card",
        shape === "text" && "h-4 w-full rounded-chip",
        className,
      )}
      {...props}
    />
  );
}

/**
 * Wraps a loading region so assistive tech announces it once, instead of
 * announcing every individual placeholder.
 *
 * Skeletons themselves carry no ARIA — they are decorative. The container is
 * what carries the meaning.
 */
export function SkeletonGroup({
  label = "Loading",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { label?: string }) {
  return (
    <div
      aria-busy="true"
      aria-live="polite"
      aria-label={label}
      className={className}
      {...props}
    >
      {children}
    </div>
  );
}

export default Skeleton;

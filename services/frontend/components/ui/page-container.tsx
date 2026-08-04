import React from "react";
import { cn } from "@/lib/cn";

/*
 * Every authenticated page previously hand-wrote its own
 * `<main className="flex-1 p-8 md:p-12 max-w-Nxl mx-auto">` with a slightly
 * different max-width and no shared name for the pattern. This is that
 * pattern, extracted once, so page width and gutter stay consistent as new
 * screens are added.
 */

const SIZE = {
  md: "max-w-3xl",
  lg: "max-w-4xl",
  xl: "max-w-5xl",
  "2xl": "max-w-6xl",
  full: "max-w-none",
} as const;

export interface PageContainerProps
  extends Omit<React.HTMLAttributes<HTMLElement>, "className"> {
  size?: keyof typeof SIZE;
  className?: string;
  /** Render as a plain div instead of a <main> landmark, for pages that already provide their own. */
  as?: "main" | "div";
}

export function PageContainer({
  size = "lg",
  as = "main",
  className,
  children,
  ...props
}: PageContainerProps) {
  const Component = as;
  return (
    <Component
      className={cn(
        "mx-auto w-full flex-1 p-6 md:p-10 lg:p-12",
        SIZE[size],
        className,
      )}
      {...props}
    >
      {children}
    </Component>
  );
}

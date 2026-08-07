import React from "react";
import { cn } from "@/lib/cn";

/**
 * Above-the-fold entrance animation. Pure CSS, no JS, no client boundary.
 *
 * `Reveal` must NOT be used above the fold. It ships `opacity: 0` in the HTML
 * and only clears it once React has hydrated and the IntersectionObserver has
 * fired — which pushed the hero's Largest Contentful Paint to 3.9s, 88% of it
 * "render delay", because the LCP element was waiting on JavaScript before it
 * could become visible at all.
 *
 * This runs off a CSS keyframe instead, so the animation begins at first paint
 * and nothing is gated on hydration. The reduced-motion rule in globals.css
 * collapses the duration to nothing.
 *
 * Rule of thumb: `Enter` above the fold, `Reveal` below it.
 */

export interface EnterProps extends React.HTMLAttributes<HTMLElement> {
  /** Stagger, in ms. */
  delay?: number;
  as?: "div" | "section" | "li" | "article" | "span";
}

export function Enter({
  delay = 0,
  as: Component = "div",
  className,
  style,
  children,
  ...props
}: EnterProps) {
  const Element = Component as React.ElementType;

  return (
    <Element
      style={{ ...style, animationDelay: `${delay}ms` }}
      className={cn("animate-fade-up", className)}
      {...props}
    >
      {children}
    </Element>
  );
}

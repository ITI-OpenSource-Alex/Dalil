"use client";

import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Reveals its children when they scroll into view, once.
 *
 * Deliberately NOT framer-motion. This is ~1kB of behaviour against
 * framer-motion's ~34kB, and it runs on the product's highest-traffic
 * surface. The visual result -- a 16px rise and fade on the house easing --
 * is identical.
 *
 * `children` are passed through untouched, so everything inside stays a
 * Server Component. Only this wrapper hydrates.
 *
 * The hidden state ships in the HTML (see [data-reveal] in globals.css) so
 * there is no flash of unrevealed content. app/page.tsx carries a <noscript>
 * override so the page is fully readable if JS never runs.
 */

export interface RevealProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Stagger, in ms. Use multiples of ~60 for sibling groups. */
  delay?: number;
  /** How much of the element must be visible before it reveals. */
  amount?: number;
  as?: "div" | "section" | "li" | "article";
}

export function Reveal({
  delay = 0,
  amount = 0.2,
  as: Component = "div",
  className,
  style,
  children,
  ...props
}: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    // Elements already in view on load (the hero, above the fold) should not
    // wait for a scroll event that may never come.
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.setAttribute("data-reveal", "visible");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: amount, rootMargin: "0px 0px -5% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [amount]);

  const Element = Component as React.ElementType;

  return (
    <Element
      ref={ref}
      data-reveal="hidden"
      style={{ ...style, "--reveal-delay": `${delay}ms` } as React.CSSProperties}
      className={cn(className)}
      {...props}
    >
      {children}
    </Element>
  );
}

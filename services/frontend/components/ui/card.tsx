import React from "react";
import { cn } from "@/lib/cn";
import { Heading, type HeadingProps } from "./heading";
import { Text } from "./text";

/* ------------------------------------------------------------------ *
 * One card, three roles. The audit found shadow-2xs (28 uses), shadow-sm
 * (22) and shadow-xl used interchangeably for the *same* card role on
 * different pages. `variant` makes that a decision rather than a habit.
 * ------------------------------------------------------------------ */

export type CardVariant = "flat" | "raised" | "interactive" | "inverse";

const VARIANT: Record<CardVariant, string> = {
  // Default. Separation comes from the border, not from a shadow.
  flat: "border border-border bg-surface",
  raised: "border border-border bg-surface shadow-e1",
  // For cards that are themselves a link or button. The lift on hover is the
  // affordance; without it a clickable card looks identical to a static one.
  interactive:
    "border border-border bg-surface shadow-e1 transition-[box-shadow,border-color,transform] duration-200 ease-out hover:-translate-y-0.5 hover:border-border-strong hover:shadow-e2 active:translate-y-0 active:shadow-e1",
  inverse: "border border-border-inverse bg-surface-inverse",
};

const PADDING = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
} as const;

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  /**
   * Applied to the card itself. Use `none` when composing with CardHeader /
   * CardBody / CardFooter, which bring their own padding and dividers.
   */
  padding?: keyof typeof PADDING;
  /** Renders as <article>, <section> or <li> where that is the honest element. */
  as?: "div" | "article" | "section" | "li";
}

export function Card({
  variant = "flat",
  padding = "md",
  as: Component = "div",
  className,
  children,
  ...props
}: CardProps) {
  // The element type is chosen at runtime, so TS cannot narrow the event
  // handler types to one specific element. The props are structurally
  // compatible for every member of the `as` union; only the handler element
  // generics differ.
  const Element = Component as React.ElementType;

  return (
    <Element
      className={cn(
        "rounded-card",
        VARIANT[variant],
        PADDING[padding],
        className,
      )}
      {...props}
    >
      {children}
    </Element>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("flex flex-col gap-1 p-6 pb-0", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({
  as = "h3",
  size = "md",
  className,
  children,
  ...props
}: HeadingProps) {
  return (
    <Heading as={as} size={size} className={className} {...props}>
      {children}
    </Heading>
  );
}

export function CardDescription({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <Text size="sm" tone="muted" className={className} {...props}>
      {children}
    </Text>
  );
}

export function CardBody({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("p-6", className)} {...props}>
      {children}
    </div>
  );
}

export interface CardFooterProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Tints and rules off the footer, for action bars. */
  divided?: boolean;
}

export function CardFooter({
  divided = false,
  className,
  children,
  ...props
}: CardFooterProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3 p-6 pt-0",
        divided && "mt-6 border-t border-border bg-canvas-subtle pt-6",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

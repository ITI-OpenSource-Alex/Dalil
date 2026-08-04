import React from "react";
import { cn } from "@/lib/cn";
import { Eyebrow, Heading, Text } from "@/components/ui";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * The page's rhythm, in one place.
 *
 * Every marketing section uses the same vertical scale and the same
 * container, so the spacing between sections is a property of the page
 * rather than a per-file guess. The previous landing page set py-24 flat
 * on every section at every breakpoint, which is why it read as a stack
 * of boxes rather than a composition.
 *
 * `tone` is what creates the light/dark rhythm down the page: the two
 * inverse sections (Proof at the midpoint, CTA at the close) are the
 * page's visual anchors.
 * ------------------------------------------------------------------ */

export type SectionTone = "canvas" | "subtle" | "surface" | "inverse";

const TONE: Record<SectionTone, string> = {
  canvas: "bg-canvas",
  subtle: "bg-canvas-subtle",
  surface: "bg-surface",
  inverse: "bg-surface-inverse",
};

const SIZE = {
  // Scales with the viewport instead of sitting at a flat py-24. The jump
  // from 80px to 128px is what gives large screens room to breathe.
  default: "py-20 sm:py-24 lg:py-32",
  compact: "py-14 sm:py-16 lg:py-20",
  tight: "py-8 sm:py-10",
} as const;

export interface SectionProps extends React.HTMLAttributes<HTMLElement> {
  tone?: SectionTone;
  size?: keyof typeof SIZE;
  /** Id of the heading that names this section, for aria-labelledby. */
  labelledBy?: string;
}

export function Section({
  tone = "canvas",
  size = "default",
  labelledBy,
  className,
  children,
  ...props
}: SectionProps) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={cn("relative isolate", TONE[tone], SIZE[size], className)}
      {...props}
    >
      {children}
    </section>
  );
}

export function Container({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mx-auto w-full max-w-6xl px-6 lg:px-8", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export interface SectionHeaderProps {
  id: string;
  eyebrow: string;
  title: React.ReactNode;
  lead?: React.ReactNode;
  /**
   * Content sections read left-aligned; the two "moment" sections (Pricing,
   * FAQ) are centred. Mixing the two deliberately is what stops the page
   * looking like a template, where everything is centred by default.
   */
  align?: "left" | "center";
  tone?: "default" | "inverse";
  className?: string;
}

export function SectionHeader({
  id,
  eyebrow,
  title,
  lead,
  align = "left",
  tone = "default",
  className,
}: SectionHeaderProps) {
  const inverse = tone === "inverse";

  return (
    <Reveal
      className={cn(
        "flex flex-col",
        align === "center" && "items-center text-center",
        className,
      )}
    >
      <Eyebrow tone={inverse ? "inverse-muted" : "brand"}>{eyebrow}</Eyebrow>

      <Heading
        as="h2"
        id={id}
        size="2xl"
        tone={inverse ? "inverse" : "default"}
        className={cn("mt-4 max-w-2xl", align === "center" && "mx-auto")}
      >
        {title}
      </Heading>

      {lead && (
        <Text
          size="lg"
          tone={inverse ? "inverse-muted" : "muted"}
          className={cn("mt-5 max-w-xl", align === "center" && "mx-auto")}
        >
          {lead}
        </Text>
      )}
    </Reveal>
  );
}

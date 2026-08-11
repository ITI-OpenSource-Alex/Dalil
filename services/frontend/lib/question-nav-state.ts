import { cn } from "@/lib/cn";

/** Circle classes for the Reading question map (Approach 1 states). */
export function navCircleClassName({
  answered,
  active,
}: {
  answered: boolean;
  active: boolean;
}): string {
  return cn(
    "flex h-8 w-8 items-center justify-center rounded-full border text-xs font-semibold transition",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted",
    answered
      ? "border-brand bg-brand text-fg-on-brand"
      : "border-border-strong bg-surface text-fg-muted hover:bg-canvas-subtle",
    active && "border-brand ring-2 ring-brand-muted",
  );
}

/** Accessible name: "Question 3, answered, current" etc. */
export function navCircleAriaLabel({
  questionNumber,
  answered,
  active,
}: {
  questionNumber: number;
  answered: boolean;
  active: boolean;
}): string {
  const parts = [
    `Question ${questionNumber}`,
    answered ? "answered" : "unanswered",
  ];
  if (active) parts.push("current");
  return parts.join(", ");
}

/** Mini swatch classes for the map legend (decorative). */
export function navLegendSwatchClassName(
  kind: "current" | "answered" | "unanswered",
): string {
  return cn(
    "inline-block h-3 w-3 shrink-0 rounded-full border",
    kind === "answered" && "border-brand bg-brand",
    kind === "unanswered" && "border-border-strong bg-surface",
    kind === "current" &&
      "border-brand bg-surface ring-2 ring-brand-muted ring-offset-1 ring-offset-canvas-subtle",
  );
}

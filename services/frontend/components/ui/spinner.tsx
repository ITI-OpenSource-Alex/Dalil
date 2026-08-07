import { cn } from "@/lib/cn";
import { ICON_SIZE, type IconSize } from "./icon";

export interface SpinnerProps extends React.SVGProps<SVGSVGElement> {
  size?: IconSize;
  /**
   * Accessible name announced while busy. Pass `null` when the spinner sits
   * inside a control that already communicates its own busy state (Button
   * sets aria-busy), so the state isn't announced twice.
   */
  label?: string | null;
}

/**
 * Indeterminate loading indicator.
 *
 * Pure SVG + CSS rotation, no JS and no layout cost. The reduced-motion rule
 * in globals.css slows the rotation to a stop for users who ask for it, so
 * the shape still reads as "busy" without spinning.
 */
export function Spinner({
  size = "sm",
  label = "Loading",
  className,
  ...props
}: SpinnerProps) {
  const px = ICON_SIZE[size];

  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      role={label ? "status" : undefined}
      aria-label={label ?? undefined}
      aria-hidden={label ? undefined : true}
      className={cn("shrink-0 animate-spin", className)}
      {...props}
    >
      {/* Track */}
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        opacity="0.25"
      />
      {/* Arc — one quarter turn, which is what makes rotation legible */}
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

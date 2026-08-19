import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Icon sizes, in px. Four steps only.
 *
 * Before this existed, icon sizes were chosen per call site -- size={16},
 * {18}, {22}, {24} all appear in the codebase with no rule -- which is why
 * icons never optically align between sections.
 *
 * xs/sm pair with text-xs/text-sm, md with text-base, lg with headings.
 */
export const ICON_SIZE = {
  xs: 14,
  sm: 16,
  md: 20,
  lg: 24,
} as const;

export type IconSize = keyof typeof ICON_SIZE;

export interface IconProps extends Omit<React.SVGProps<SVGSVGElement>, "ref"> {
  /** Any lucide-react icon, passed as a component reference: `icon={Check}`. */
  icon: LucideIcon;
  size?: IconSize;
  /**
   * Accessible name. Provide this ONLY when the icon carries meaning that no
   * adjacent text conveys -- a standalone status marker, for instance.
   *
   * Omit it for the common case where the icon sits beside a visible label or
   * inside a button that already has an accessible name; the icon is then
   * marked aria-hidden so screen readers don't announce it twice.
   */
  label?: string;
}

export function Icon({
  icon: Component,
  size = "sm",
  label,
  className,
  ...props
}: IconProps) {
  const px = ICON_SIZE[size];

  return (
    <Component
      width={px}
      height={px}
      // Pinned so icons keep a consistent optical weight across sizes;
      // lucide's default of 2 looks heavy at 14px and thin at 24px.
      strokeWidth={size === "lg" ? 1.75 : 2}
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      // shrink-0 stops icons being squashed inside flex rows with long labels,
      // which is the single most common icon bug in this codebase.
      className={cn("shrink-0", className)}
      {...props}
    />
  );
}

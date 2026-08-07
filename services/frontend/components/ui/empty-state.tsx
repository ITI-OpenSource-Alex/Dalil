import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { Heading } from "./heading";
import { Text } from "./text";

/**
 * The state a screen is in before it has anything to show.
 *
 * Distinct from an error: nothing has gone wrong, so the tone is
 * instructional, not apologetic, and the primary job is to offer the action
 * that would fill the screen. An empty state without an action is a dead end.
 *
 * The audit found no empty-state treatment anywhere in the codebase — lists
 * with no items currently render as blank space.
 */

const SIZE = {
  sm: { wrap: "py-8", icon: "h-10 w-10", gap: "gap-3" },
  md: { wrap: "py-14", icon: "h-12 w-12", gap: "gap-4" },
  lg: { wrap: "py-20", icon: "h-14 w-14", gap: "gap-4" },
} as const;

// See the note in alert.tsx: `title` here is rendered content, not the
// native string tooltip attribute.
export interface EmptyStateProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: LucideIcon;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Primary and secondary actions. */
  actions?: React.ReactNode;
  size?: keyof typeof SIZE;
  /** Adds a dashed container, for empty states that sit inside a panel. */
  bordered?: boolean;
}

export function EmptyState({
  icon,
  title,
  description,
  actions,
  size = "md",
  bordered = false,
  className,
  children,
  ...props
}: EmptyStateProps) {
  const s = SIZE[size];

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center px-6 text-center",
        s.wrap,
        s.gap,
        bordered && "rounded-card border border-dashed border-border-strong",
        className,
      )}
      {...props}
    >
      {icon && (
        <span
          className={cn(
            "flex items-center justify-center rounded-full bg-brand-muted text-brand-fg",
            s.icon,
          )}
        >
          <Icon icon={icon} size="md" />
        </span>
      )}

      <div className="flex max-w-sm flex-col gap-1.5">
        <Heading as="h3" size="sm">
          {title}
        </Heading>
        {description && (
          <Text size="sm" tone="muted">
            {description}
          </Text>
        )}
      </div>

      {children}

      {actions && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-3">
          {actions}
        </div>
      )}
    </div>
  );
}

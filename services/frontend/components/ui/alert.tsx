import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  X,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { Button } from "./button";

/* ------------------------------------------------------------------ *
 * Absorbs three separate error-banner implementations that are visually
 * different for identical purposes: profile/page.tsx, ChecklistView.tsx
 * and speaking/inline-alert.tsx.
 *
 * No "use client": dismissal is controlled by the caller via onDismiss,
 * so this stays renderable from a Server Component when it is static.
 * ------------------------------------------------------------------ */

export type AlertTone = "info" | "success" | "warning" | "danger";

const TONE: Record<
  AlertTone,
  { box: string; icon: string; title: string; body: string; defaultIcon: LucideIcon }
> = {
  info: {
    box: "border-info-border bg-info-subtle",
    icon: "text-info",
    title: "text-info-fg",
    body: "text-info-fg/90",
    defaultIcon: Info,
  },
  success: {
    box: "border-success-border bg-success-subtle",
    icon: "text-success",
    title: "text-success-fg",
    body: "text-success-fg/90",
    defaultIcon: CheckCircle2,
  },
  warning: {
    box: "border-warning-border bg-warning-subtle",
    icon: "text-warning",
    title: "text-warning-fg",
    body: "text-warning-fg/90",
    defaultIcon: AlertTriangle,
  },
  danger: {
    box: "border-danger-border bg-danger-subtle",
    icon: "text-danger",
    title: "text-danger-fg",
    body: "text-danger-fg/90",
    defaultIcon: XCircle,
  },
};

// `title` is omitted from the DOM attributes it extends: the native title
// attribute is a string tooltip, whereas this component's title is rendered
// content and accepts nodes. Keeping both under one name would silently make
// the prop string-only.
export interface AlertProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  tone?: AlertTone;
  title?: React.ReactNode;
  /** Replaces the tone's default icon. Pass `null` to render none. */
  icon?: LucideIcon | null;
  /** Buttons or links. Rendered under the body with consistent spacing. */
  actions?: React.ReactNode;
  /** Shows a close button. Presence of the handler is what enables it. */
  onDismiss?: () => void;
  dismissLabel?: string;
  /**
   * Overrides the announcement politeness.
   *
   * Defaults: `danger` announces assertively (role="alert") because it
   * reports a failure the user must act on; every other tone announces
   * politely (role="status") so it doesn't interrupt what is being read.
   * Pass "none" for alerts rendered statically on page load, which should
   * not be announced as if they had just appeared.
   */
  announce?: "assertive" | "polite" | "none";
}

export function Alert({
  tone = "info",
  title,
  icon,
  actions,
  onDismiss,
  dismissLabel = "Dismiss",
  announce,
  className,
  children,
  ...props
}: AlertProps) {
  const styles = TONE[tone];
  const IconComponent = icon === null ? null : (icon ?? styles.defaultIcon);

  const politeness = announce ?? (tone === "danger" ? "assertive" : "polite");

  return (
    <div
      role={
        politeness === "assertive"
          ? "alert"
          : politeness === "polite"
            ? "status"
            : undefined
      }
      className={cn(
        "flex items-start gap-3 rounded-card border p-4",
        styles.box,
        className,
      )}
      {...props}
    >
      {IconComponent && (
        <Icon
          icon={IconComponent}
          size="sm"
          className={cn("mt-0.5", styles.icon)}
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {title && (
          <p className={cn("text-sm font-semibold", styles.title)}>{title}</p>
        )}
        {children && (
          <div className={cn("text-sm leading-6", styles.body)}>{children}</div>
        )}
        {actions && (
          <div className="mt-2 flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>

      {onDismiss && (
        <Button
          variant="ghost"
          size="sm"
          iconOnly
          aria-label={dismissLabel}
          onClick={onDismiss}
          className={cn("-mt-1 -mr-1 h-8 w-8 shrink-0", styles.title)}
        >
          <Icon icon={X} size="sm" />
        </Button>
      )}
    </div>
  );
}

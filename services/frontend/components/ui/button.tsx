import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon, type IconSize } from "./icon";
import { Spinner } from "./spinner";

/* ------------------------------------------------------------------ *
 * This component deliberately has no "use client" directive, uses no
 * hooks, and attaches no event handlers of its own. That makes it a
 * *shared* component: valid inside a Server Component (so the marketing
 * pages keep shipping zero client JS) and identical in behaviour when a
 * client form imports it.
 *
 * Every capability below is therefore CSS- or attribute-driven. The one
 * place this costs us is `loading`, discussed at its prop.
 * ------------------------------------------------------------------ */

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "danger"
  | "inverse"
  | "link";

export type ButtonSize = "sm" | "md" | "lg";

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-brand text-fg-on-brand shadow-e1 hover:bg-brand-hover active:bg-brand-active",
  secondary:
    "bg-surface text-fg border border-border shadow-e1 hover:bg-canvas-subtle hover:border-border-strong active:bg-canvas-inset",
  outline:
    "border border-brand-border text-brand-fg bg-transparent hover:bg-brand-subtle active:bg-brand-muted",
  ghost:
    "text-fg-muted bg-transparent hover:bg-canvas-subtle hover:text-fg active:bg-canvas-inset",
  danger:
    "bg-danger text-white shadow-e1 hover:bg-danger-fg active:bg-danger-fg",
  // For use on --surface-inverse (the CTA band, tooltips). The focus ring is
  // re-coloured because the default forest ring is invisible on forest.
  inverse:
    "bg-surface text-brand-fg shadow-e2 hover:bg-brand-subtle active:bg-brand-muted focus-visible:outline-sand-300",
  // Renders as a button but reads as a link. No padding, so it aligns with
  // surrounding text rather than sitting in its own box.
  link: "text-brand-fg underline underline-offset-4 decoration-brand-border hover:decoration-brand-fg active:text-brand-active",
};

const SIZE: Record<ButtonSize, string> = {
  // h-11 (44px) is the default because it is the WCAG 2.5.5 target size;
  // sm is reserved for dense toolbars where a 36px control is defensible.
  sm: "h-9 gap-1.5 px-3 text-sm",
  md: "h-11 gap-2 px-4 text-sm",
  lg: "h-12 gap-2 px-6 text-base",
};

const ICON_ONLY_SIZE: Record<ButtonSize, string> = {
  sm: "h-9 w-9 p-0",
  md: "h-11 w-11 p-0",
  lg: "h-12 w-12 p-0",
};

const ICON_FOR_SIZE: Record<ButtonSize, IconSize> = {
  sm: "xs",
  md: "sm",
  lg: "sm",
};

const BASE =
  // Layout
  "relative inline-flex items-center justify-center whitespace-nowrap align-middle " +
  // Type
  "font-semibold " +
  // Shape — role-named radius token, not a numeric one
  "rounded-control " +
  // Motion: named properties only. A bare `transition` animates every
  // property including layout ones, which is the codebase's current default.
  "transition-[background-color,border-color,color,box-shadow,transform] duration-120 ease-out " +
  "active:scale-[0.98] " +
  // Disabled.
  "disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none " +
  // ...but a *busy* button is not an unavailable one. `loading` uses the
  // native disabled attribute to prevent double submission, which would
  // otherwise also fade the button to 50% and leave a barely-visible spinner.
  // Restoring full opacity keeps it reading as "working" rather than "off".
  "aria-busy:opacity-100 " +
  // Icons inside never shrink or capture the click target
  "[&_svg]:pointer-events-none";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Stretches to the container width. Common for form submits and mobile. */
  fullWidth?: boolean;
  /**
   * Busy state. Sets `aria-busy`, swaps in a spinner, and disables the
   * control so a slow request cannot be double-submitted.
   *
   * The label is kept in the DOM at `invisible` rather than replaced, so the
   * button does not change width when it enters the loading state — a
   * form whose submit button resizes mid-request is a layout-shift bug.
   *
   * Trade-off: this uses the native `disabled` attribute, which drops focus.
   * The alternative (aria-disabled plus a JS click guard) keeps focus but
   * would force this component to be client-side, costing the marketing
   * pages their zero-JS property. Preventing double submission with no JS
   * is the better trade for this product.
   */
  loading?: boolean;
  /** Announced to screen readers while `loading`. */
  loadingLabel?: string;
  leadingIcon?: LucideIcon;
  trailingIcon?: LucideIcon;
  /**
   * Square, label-less button. `aria-label` becomes required at the type
   * level, because an icon-only control with no accessible name is the most
   * common a11y defect in a component library.
   */
  iconOnly?: boolean;
  /**
   * Renders the child element instead of a `<button>`, merging styling and
   * props onto it. Use for links that should look like buttons:
   *
   *   <Button asChild><Link href="/register">Get started</Link></Button>
   *
   * Implemented with cloneElement rather than @radix-ui/react-slot because
   * Slot is a client component and would pull this whole component — and
   * every marketing page using it — across the server/client boundary.
   */
  asChild?: boolean;
}

type IconOnlyProps = ButtonProps & { iconOnly: true; "aria-label": string };

export function Button(props: ButtonProps | IconOnlyProps) {
  const {
    variant = "primary",
    size = "md",
    fullWidth = false,
    loading = false,
    loadingLabel = "Loading",
    leadingIcon,
    trailingIcon,
    iconOnly = false,
    asChild = false,
    className,
    children,
    disabled,
    type,
    ...rest
  } = props;

  const classes = cn(
    BASE,
    VARIANT[variant],
    variant === "link"
      ? "h-auto gap-1 p-0 active:scale-100"
      : iconOnly
        ? ICON_ONLY_SIZE[size]
        : SIZE[size],
    fullWidth && "w-full",
    className,
  );

  const iconSize = ICON_FOR_SIZE[size];

  const content = (childContent: React.ReactNode) => (
    <>
      {loading ? (
        // Absolutely centred so it occupies no layout space, which is what
        // keeps the button's width stable between idle and busy.
        <Spinner
          size={iconSize}
          label={null}
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2"
        />
      ) : (
        leadingIcon && <Icon icon={leadingIcon} size={iconSize} />
      )}

      {childContent != null && (
        <span className={cn("inline-flex items-center", loading && "invisible")}>
          {childContent}
        </span>
      )}

      {!loading && trailingIcon && <Icon icon={trailingIcon} size={iconSize} />}

      {loading && <span className="sr-only">{loadingLabel}</span>}
    </>
  );

  if (asChild && React.isValidElement(children)) {
    const child = children as React.ReactElement<
      Record<string, unknown> & { className?: string; children?: React.ReactNode }
    >;

    return React.cloneElement(
      child,
      {
        ...rest,
        className: cn(classes, child.props.className),
        "aria-busy": loading || undefined,
        // An anchor cannot be natively disabled; aria-disabled plus removal
        // from the tab order is the accessible equivalent.
        ...(disabled || loading
          ? { "aria-disabled": true, tabIndex: -1 }
          : null),
      },
      content(child.props.children),
    );
  }

  return (
    <button
      // Defaulting to "button" prevents the classic bug where a button inside
      // a form submits it by accident. Callers opt into type="submit".
      type={type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={classes}
      {...rest}
    >
      {content(children)}
    </button>
  );
}

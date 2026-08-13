"use client";

import React from "react";
import { cn } from "@/lib/cn";
import { useFieldControl } from "./field";

/**
 * Toggle for a setting that applies immediately.
 *
 * If the change needs a Save button to take effect, use a Checkbox instead —
 * a switch that doesn't take effect until submit is a well-known usability
 * trap.
 *
 * Implemented as a checkbox input with role="switch", so it keeps native
 * keyboard behaviour (Space toggles) and form participation while being
 * announced as "on"/"off" rather than "checked"/"unchecked".
 */

export interface SwitchProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "onChange" | "type" | "size"
  > {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  label?: string;
  children?: React.ReactNode;
  description?: React.ReactNode;
  /** Label on the left, control on the right — the settings-row layout. */
  align?: "start" | "between";
}

export function Switch({
  checked,
  onChange,
  label,
  children,
  description,
  align = "start",
  className,
  id,
  disabled,
  ...props
}: SwitchProps) {
  const { invalid: _invalid, ...aria } = useFieldControl({ id, disabled });

  const control = (
    <span className="relative inline-flex shrink-0 items-center">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange?.(e.target.checked)}
        aria-label={children ? undefined : label}
        {...aria}
        {...props}
        className={cn(
          "peer h-6 w-11 cursor-pointer appearance-none rounded-full border border-transparent bg-border-strong",
          "transition-colors duration-200 ease-out",
          "checked:bg-brand hover:bg-fg-subtle checked:hover:bg-brand-hover",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      />
      {/* Thumb. translate-x rather than left, so it animates on the compositor. */}
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute left-0.5 h-5 w-5 rounded-full bg-white shadow-e1",
          "transition-transform duration-200 ease-out",
          "peer-checked:translate-x-5",
        )}
      />
    </span>
  );

  if (!children) return <span className={className}>{control}</span>;

  return (
    <label
      className={cn(
        "flex items-start gap-3",
        align === "between" && "w-full justify-between",
        disabled ? "cursor-not-allowed" : "cursor-pointer",
        className,
      )}
    >
      {align === "between" ? (
        <>
          <span className="flex flex-col gap-0.5">
            <span
              className={cn(
                "text-sm leading-5 font-medium",
                disabled ? "text-fg-subtle" : "text-fg",
              )}
            >
              {children}
            </span>
            {description && (
              <span className="text-sm leading-5 text-fg-subtle">
                {description}
              </span>
            )}
          </span>
          {control}
        </>
      ) : (
        <>
          {control}
          <span className="flex flex-col gap-0.5">
            <span
              className={cn(
                "text-sm leading-5 font-medium",
                disabled ? "text-fg-subtle" : "text-fg",
              )}
            >
              {children}
            </span>
            {description && (
              <span className="text-sm leading-5 text-fg-subtle">
                {description}
              </span>
            )}
          </span>
        </>
      )}
    </label>
  );
}

"use client";

import React from "react";
import { cn } from "@/lib/cn";

/* Native <input type="radio">, for the same reasons as Checkbox: arrow-key
   navigation within a group, form participation and correct announcement all
   come from the platform. Grouping is done with a real <fieldset>/<legend>,
   which is what makes screen readers announce "2 of 4" while arrowing. */

const DOT =
  "peer h-5 w-5 shrink-0 appearance-none rounded-full border bg-surface " +
  "transition-[background-color,border-color] duration-120 ease-out " +
  "border-border-strong hover:border-brand " +
  "checked:border-[6px] checked:border-brand " +
  "disabled:cursor-not-allowed disabled:border-border disabled:bg-canvas-inset " +
  "disabled:checked:border-fg-subtle";

export interface RadioProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "size"> {
  label?: string;
  children?: React.ReactNode;
  description?: React.ReactNode;
}

export function Radio({
  label,
  children,
  description,
  className,
  disabled,
  ...props
}: RadioProps) {
  const dot = (
    <input
      type="radio"
      disabled={disabled}
      aria-label={children ? undefined : label}
      {...props}
      className={cn(DOT, !children && className)}
    />
  );

  if (!children) return dot;

  return (
    <label
      className={cn(
        "flex items-start gap-3",
        disabled ? "cursor-not-allowed" : "cursor-pointer",
        className,
      )}
    >
      {dot}
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
          <span className="text-sm leading-5 text-fg-subtle">{description}</span>
        )}
      </span>
    </label>
  );
}

export interface RadioGroupProps
  extends React.FieldsetHTMLAttributes<HTMLFieldSetElement> {
  legend: React.ReactNode;
  /** Hides the legend visually while keeping the group announced. */
  legendHidden?: boolean;
  hint?: React.ReactNode;
  orientation?: "vertical" | "horizontal";
}

export function RadioGroup({
  legend,
  legendHidden = false,
  hint,
  orientation = "vertical",
  className,
  children,
  ...props
}: RadioGroupProps) {
  return (
    // A fieldset, not a div with role="radiogroup": the native pairing of
    // fieldset/legend is what associates the group name with each option.
    <fieldset className={cn("flex flex-col gap-3", className)} {...props}>
      <legend
        className={cn(
          "text-sm font-medium text-fg",
          legendHidden && "sr-only",
          !legendHidden && "mb-1",
        )}
      >
        {legend}
      </legend>
      {hint && <p className="-mt-1 text-sm text-fg-subtle">{hint}</p>}
      <div
        className={cn(
          "flex gap-3",
          orientation === "vertical" ? "flex-col" : "flex-row flex-wrap gap-x-6",
        )}
      >
        {children}
      </div>
    </fieldset>
  );
}

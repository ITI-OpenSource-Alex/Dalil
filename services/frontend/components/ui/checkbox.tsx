"use client";

import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import { useFieldControl } from "./field";

/* ------------------------------------------------------------------ *
 * Built on a real <input type="checkbox">, not the <button role="checkbox">
 * this previously was.
 *
 * The native element brings keyboard handling, form participation, the
 * indeterminate state and correct announcement in every screen reader for
 * free. It is styled via appearance-none rather than replaced, so none of
 * that is given up.
 *
 * The previous prop API ({ checked, onChange, disabled, label }) and the
 * default export are both preserved -- ChecklistItemRow and its unit test
 * depend on them.
 * ------------------------------------------------------------------ */

const BOX =
  "peer h-5 w-5 shrink-0 appearance-none rounded-[6px] border bg-surface " +
  "transition-[background-color,border-color] duration-120 ease-out " +
  "border-border-strong hover:border-brand " +
  "checked:border-brand checked:bg-brand " +
  "indeterminate:border-brand indeterminate:bg-brand " +
  "disabled:cursor-not-allowed disabled:border-border disabled:bg-canvas-inset " +
  "disabled:checked:border-fg-subtle disabled:checked:bg-fg-subtle";

export interface CheckboxProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "onChange" | "type" | "size"
  > {
  checked?: boolean;
  /** Receives the next checked value, not the event. */
  onChange?: (checked: boolean) => void;
  /** Accessible name. Required when no visible `children` are supplied. */
  label?: string;
  /**
   * Mixed state, for a parent controlling a group of children. This is a DOM
   * property rather than an attribute, so it is applied via a ref below.
   */
  indeterminate?: boolean;
  /** Visible label. When present, the whole row becomes the click target. */
  children?: React.ReactNode;
  /** Secondary line under the visible label. */
  description?: React.ReactNode;
}

export function Checkbox({
  checked,
  onChange,
  label,
  indeterminate = false,
  children,
  description,
  className,
  id,
  disabled,
  required,
  ...props
}: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null);
  const { invalid: _invalid, ...aria } = useFieldControl({
    id,
    disabled,
    required,
  });

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  const box = (
    <span className="relative inline-flex shrink-0 items-center justify-center">
      <input
        ref={ref}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange?.(e.target.checked)}
        aria-label={children ? undefined : label}
        {...aria}
        {...props}
        className={cn(BOX, !children && className)}
      />
      {/* Marks sit above the input and ignore pointer events, so the input
          itself always receives the click. */}
      <svg
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        className="pointer-events-none absolute h-3.5 w-3.5 scale-75 text-fg-on-brand opacity-0 transition-[opacity,transform] duration-120 ease-out peer-checked:scale-100 peer-checked:opacity-100 peer-indeterminate:opacity-0"
      >
        <path
          d="M3.5 8.5L6.5 11.5L12.5 4.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="pointer-events-none absolute h-0.5 w-2.5 rounded-full bg-fg-on-brand opacity-0 peer-indeterminate:opacity-100" />
    </span>
  );

  if (!children) return box;

  return (
    <label
      className={cn(
        "flex items-start gap-3",
        disabled ? "cursor-not-allowed" : "cursor-pointer",
        className,
      )}
    >
      {box}
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

export default Checkbox;

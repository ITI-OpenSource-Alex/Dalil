"use client";

import React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { useFieldControl } from "./field";

export type InputSize = "sm" | "md" | "lg";

/** Heights match Button so an input and a button sit level when inline. */
const SIZE: Record<InputSize, string> = {
  sm: "h-9 text-sm",
  md: "h-11 text-sm",
  lg: "h-12 text-base",
};

/**
 * Shared control skin. Exported because Textarea and Select need to look
 * identical to Input, and three copies of this string is exactly how the
 * current codebase ended up with drifting form styles.
 */
export const CONTROL_BASE =
  "w-full rounded-control border bg-surface text-fg " +
  "transition-[border-color,box-shadow] duration-120 ease-out " +
  "placeholder:text-fg-subtle " +
  // The ring is drawn with box-shadow rather than the global outline so it can
  // sit flush against the border and tint it at the same time.
  "focus-visible:outline-none focus-visible:ring-2 " +
  "disabled:cursor-not-allowed disabled:bg-canvas-subtle disabled:text-fg-subtle";

export const CONTROL_VALID =
  "border-border hover:border-border-strong focus-visible:border-brand focus-visible:ring-brand-muted";

export const CONTROL_INVALID =
  "border-danger-border bg-danger-subtle focus-visible:border-danger focus-visible:ring-danger-border";

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  inputSize?: InputSize;
  /** Overrides the surrounding Field's validity. Rarely needed. */
  invalid?: boolean;
  leadingIcon?: LucideIcon;
  /**
   * Trailing affordance — a unit, a character counter, or a control such as a
   * password visibility toggle. Rendered inside the input's box.
   */
  trailing?: React.ReactNode;
}

export function Input({
  inputSize = "md",
  invalid: invalidProp,
  leadingIcon,
  trailing,
  className,
  id,
  required,
  disabled,
  ...props
}: InputProps) {
  const field = useFieldControl({
    id,
    invalid: invalidProp,
    required,
    disabled,
  });
  const { invalid, ...aria } = field;

  const control = (
    <input
      {...aria}
      {...props}
      className={cn(
        CONTROL_BASE,
        invalid ? CONTROL_INVALID : CONTROL_VALID,
        SIZE[inputSize],
        "px-3.5",
        leadingIcon && "pl-10",
        trailing && "pr-10",
        className,
      )}
    />
  );

  if (!leadingIcon && !trailing) return control;

  return (
    <div className="relative">
      {leadingIcon && (
        <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-fg-subtle">
          <Icon icon={leadingIcon} size="sm" />
        </span>
      )}
      {control}
      {trailing && (
        <span className="absolute inset-y-0 right-0 flex items-center pr-2 text-fg-subtle">
          {trailing}
        </span>
      )}
    </div>
  );
}

export interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
  /** Lets the browser grow the box with content. Off by default. */
  autoResize?: boolean;
}

export function Textarea({
  invalid: invalidProp,
  autoResize = false,
  className,
  id,
  required,
  disabled,
  rows = 4,
  ...props
}: TextareaProps) {
  const { invalid, ...aria } = useFieldControl({
    id,
    invalid: invalidProp,
    required,
    disabled,
  });

  return (
    <textarea
      {...aria}
      {...props}
      rows={rows}
      className={cn(
        CONTROL_BASE,
        invalid ? CONTROL_INVALID : CONTROL_VALID,
        "px-3.5 py-2.5 text-sm leading-6",
        // resize-y not resize: horizontal resizing breaks the parent layout
        // and there is never a good reason to allow it.
        autoResize ? "field-sizing-content resize-none" : "resize-y",
        className,
      )}
    />
  );
}

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  selectSize?: InputSize;
  invalid?: boolean;
  /** Shown as a disabled first option when the value is empty. */
  placeholder?: string;
}

/**
 * Built on the native <select> rather than a custom listbox.
 *
 * A custom listbox is several hundred lines of roving-tabindex and typeahead
 * code to reimplement what the platform already does correctly, and it is
 * strictly worse on mobile, where the native control opens the OS picker.
 * The only thing lost is styling the option list, which is not worth it.
 */
export function Select({
  selectSize = "md",
  invalid: invalidProp,
  placeholder,
  className,
  id,
  required,
  disabled,
  children,
  ...props
}: SelectProps) {
  const { invalid, ...aria } = useFieldControl({
    id,
    invalid: invalidProp,
    required,
    disabled,
  });

  return (
    <div className="relative">
      <select
        {...aria}
        {...props}
        className={cn(
          CONTROL_BASE,
          invalid ? CONTROL_INVALID : CONTROL_VALID,
          SIZE[selectSize],
          "cursor-pointer appearance-none py-0 pr-10 pl-3.5",
          className,
        )}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {children}
      </select>
      {/* Inline chevron: an <Icon> here would need lucide imported into every
          select; a 12-byte SVG path avoids that. */}
      <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3.5 text-fg-subtle">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="m6 9 6 6 6-6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    </div>
  );
}

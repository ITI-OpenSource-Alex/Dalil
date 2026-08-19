"use client";

import React, { createContext, useContext, useId } from "react";
import { cn } from "@/lib/cn";
import { Icon } from "./icon";
import { AlertCircle } from "lucide-react";

/* ------------------------------------------------------------------ *
 * Field owns every accessible-name and description relationship for a
 * form control, so no call site can forget one.
 *
 * The audit found `aria-describedby` used exactly ZERO times across the
 * codebase: error text in LoginForm, RegisterForm and ResetPasswordForm
 * renders as an unassociated <p>, with no role="alert" and no
 * aria-invalid on the input. A screen-reader user currently gets no
 * announcement at all when a submit fails.
 *
 * Controls read this context via useFieldControl() and spread the result.
 * They also work standalone (context is null), so Input is not *forced*
 * into a Field.
 * ------------------------------------------------------------------ */

interface FieldContextValue {
  controlId: string;
  hintId: string;
  errorId: string;
  hasHint: boolean;
  invalid: boolean;
  required: boolean;
  disabled: boolean;
}

const FieldContext = createContext<FieldContextValue | null>(null);

/**
 * Props a form control should spread onto its underlying element to inherit
 * the surrounding Field's identity, validity and description wiring.
 */
export interface FieldControlProps {
  id?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
  "aria-required"?: true;
  required?: boolean;
  disabled?: boolean;
}

export function useFieldControl(overrides?: {
  id?: string;
  invalid?: boolean;
  disabled?: boolean;
  required?: boolean;
  describedBy?: string;
}): FieldControlProps & { invalid: boolean } {
  const field = useContext(FieldContext);

  const invalid = overrides?.invalid ?? field?.invalid ?? false;
  const required = overrides?.required ?? field?.required ?? false;
  const disabled = overrides?.disabled ?? field?.disabled ?? false;

  // Order matters: the hint is read before the error, matching visual order.
  const describedBy =
    [
      field?.hasHint ? field.hintId : null,
      invalid && field ? field.errorId : null,
      overrides?.describedBy ?? null,
    ]
      .filter(Boolean)
      .join(" ") || undefined;

  return {
    id: overrides?.id ?? field?.controlId,
    "aria-describedby": describedBy,
    "aria-invalid": invalid || undefined,
    // aria-required rather than only the native attribute, so the requirement
    // is announced even on controls where `required` isn't natively supported.
    "aria-required": required || undefined,
    required: required || undefined,
    disabled: disabled || undefined,
    invalid,
  };
}

export interface FieldProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "children"> {
  label: React.ReactNode;
  /** Helper text shown under the label, before the control. */
  hint?: React.ReactNode;
  /** When set, the field renders as invalid and this text is announced. */
  error?: string | null;
  required?: boolean;
  disabled?: boolean;
  /**
   * Hides the label visually while keeping it available to screen readers.
   * Use sparingly -- a visible label is almost always the better design.
   */
  labelHidden?: boolean;
  /** Explicit id, when a control needs a stable one (tests, deep links). */
  id?: string;
  children: React.ReactNode;
}

export function Field({
  label,
  hint,
  error,
  required = false,
  disabled = false,
  labelHidden = false,
  id,
  className,
  children,
  ...props
}: FieldProps) {
  const generatedId = useId();
  const controlId = id ?? `field-${generatedId}`;
  const invalid = Boolean(error);

  const value: FieldContextValue = {
    controlId,
    hintId: `${controlId}-hint`,
    errorId: `${controlId}-error`,
    hasHint: Boolean(hint),
    invalid,
    required,
    disabled,
  };

  return (
    <FieldContext.Provider value={value}>
      <div className={cn("flex flex-col gap-1.5", className)} {...props}>
        <label
          htmlFor={controlId}
          className={cn(
            "text-sm font-medium",
            disabled ? "text-fg-subtle" : "text-fg",
            labelHidden && "sr-only",
          )}
        >
          {label}
          {required && (
            <>
              {/* The asterisk is decorative: the requirement itself is
                  conveyed to assistive tech by aria-required on the control,
                  so announcing "asterisk" here would be noise. */}
              <span aria-hidden="true" className="ml-0.5 text-danger">
                *
              </span>
              <span className="sr-only"> (required)</span>
            </>
          )}
        </label>

        {hint && (
          <p id={value.hintId} className="text-sm leading-5 text-fg-subtle">
            {hint}
          </p>
        )}

        {children}

        {error && (
          // role="alert" makes this announce the moment it mounts, which is
          // what turns a silent failed submit into a perceivable one.
          <p
            id={value.errorId}
            role="alert"
            className="flex items-start gap-1.5 text-sm leading-5 text-danger-fg"
          >
            <Icon icon={AlertCircle} size="xs" className="mt-0.5" />
            <span>{error}</span>
          </p>
        )}
      </div>
    </FieldContext.Provider>
  );
}

"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon, Progress } from "@/components/ui";

export const ONBOARDING_STEPS = [
  "Academic background",
  "English proficiency",
  "Target programmes",
] as const;

/**
 * Replaces the manual percentage-width bar in the previous wizard, which
 * exposed no value to assistive technology at all. The full stepper (circles
 * + connecting rail) is the sm+ treatment; below that there isn't room for
 * three labels, so it collapses to the same Progress bar plus "Step X of 3".
 *
 * Completed steps are clickable when `onStepSelect` is supplied. Going back to
 * fix an answer previously meant pressing Back repeatedly, and the numbered
 * circles *looked* interactive while doing nothing — an affordance that lies.
 * Forward steps stay inert: they are gated on validation, and a stepper is not
 * the place to discover that.
 */
export function OnboardingStepper({
  currentStep,
  onStepSelect,
}: {
  currentStep: number;
  onStepSelect?: (step: number) => void;
}) {
  const total = ONBOARDING_STEPS.length;

  return (
    <div className="mb-8">
      <ol className="hidden items-start sm:flex">
        {ONBOARDING_STEPS.map((label, index) => {
          const step = index + 1;
          const state = step < currentStep ? "done" : step === currentStep ? "current" : "upcoming";
          const navigable = state === "done" && Boolean(onStepSelect);

          const marker = (
            <span
              aria-hidden="true"
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors duration-200 ease-out",
                state === "done" && "bg-brand text-fg-on-brand",
                state === "current" && "bg-brand-muted text-brand-fg ring-2 ring-brand",
                state === "upcoming" && "bg-canvas-inset text-fg-subtle",
                navigable && "hover:bg-brand-hover",
              )}
            >
              {state === "done" ? <Icon icon={Check} size="xs" /> : step}
            </span>
          );

          return (
            <li key={label} className="flex flex-1 flex-col items-center gap-2 last:flex-none">
              <div className="flex w-full items-center">
                {navigable ? (
                  <button
                    type="button"
                    onClick={() => onStepSelect?.(step)}
                    aria-label={`Go back to step ${step}: ${label}`}
                    className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
                  >
                    {marker}
                  </button>
                ) : (
                  marker
                )}
                {step < total && (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "mx-2 h-0.5 flex-1 rounded-full transition-colors duration-200 ease-out",
                      state === "done" ? "bg-brand" : "bg-border",
                    )}
                  />
                )}
              </div>
              <span
                className={cn(
                  "max-w-26 text-center text-xs font-medium",
                  state === "upcoming" ? "text-fg-subtle" : "text-fg",
                )}
              >
                {label}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="sm:hidden">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <span className="text-xs font-semibold tracking-wide text-brand-fg uppercase">
            Step {currentStep} of {total}
          </span>
          <span className="truncate text-sm font-medium text-fg">
            {ONBOARDING_STEPS[currentStep - 1]}
          </span>
        </div>
        {currentStep < total && (
          <p className="mb-1 text-xs text-fg-subtle">
            Next: {ONBOARDING_STEPS[currentStep]}
          </p>
        )}
      </div>

      <Progress
        value={currentStep}
        max={total}
        label="Onboarding progress"
        valueText={`Step ${currentStep} of ${total}`}
        className="mt-4 sm:mt-3"
      />
    </div>
  );
}

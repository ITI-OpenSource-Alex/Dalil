import { Check } from "lucide-react";
import { cn } from "@/lib/cn";
import { Icon, Progress } from "@/components/ui";

export const ONBOARDING_STEPS = [
  "Academic background",
  "English proficiency",
  "Target programmes",
  "Upload CV",
] as const;

/**
 * Replaces the manual percentage-width bar in the previous wizard, which
 * exposed no value to assistive technology at all. The full stepper (circles
 * + connecting rail) is the sm+ treatment; below that there isn't room for
 * four labels, so it collapses to the same Progress bar plus "Step X of 4".
 */
export function OnboardingStepper({ currentStep }: { currentStep: number }) {
  const total = ONBOARDING_STEPS.length;

  return (
    <div className="mb-8">
      <ol className="hidden items-start sm:flex">
        {ONBOARDING_STEPS.map((label, index) => {
          const step = index + 1;
          const state = step < currentStep ? "done" : step === currentStep ? "current" : "upcoming";

          return (
            <li key={label} className="flex flex-1 flex-col items-center gap-2 last:flex-none">
              <div className="flex w-full items-center">
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors duration-200 ease-out",
                    state === "done" && "bg-brand text-fg-on-brand",
                    state === "current" && "bg-brand-muted text-brand-fg ring-2 ring-brand",
                    state === "upcoming" && "bg-canvas-inset text-fg-subtle",
                  )}
                >
                  {state === "done" ? <Icon icon={Check} size="xs" /> : step}
                </span>
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
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs font-semibold tracking-wide text-brand-fg uppercase">
            Step {currentStep} of {total}
          </span>
          <span className="text-sm font-medium text-fg">
            {ONBOARDING_STEPS[currentStep - 1]}
          </span>
        </div>
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

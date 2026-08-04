import { cn } from "@/lib/cn";

/**
 * A radio option styled as a selectable card rather than a bare dot --
 * carries the same native <input type="radio"> semantics (grouping, arrow-key
 * navigation, form participation) as components/ui/radio.tsx, just visually
 * heavier for the wizard's binary choices. Kept local to onboarding rather
 * than promoted to components/ui because it has exactly one consumer shape:
 * two-option "yes/no"-style groups with a short label.
 */
export function ChoiceCard({
  name,
  value,
  checked,
  onChange,
  children,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  children: React.ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-between gap-3 rounded-control border p-3 text-sm font-medium transition-colors duration-120 ease-out",
        checked
          ? "border-brand bg-brand-subtle text-fg ring-1 ring-brand"
          : "border-border text-fg-muted hover:border-border-strong hover:bg-canvas-subtle",
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <span>{children}</span>
      <span
        aria-hidden="true"
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
          checked ? "border-[5px] border-brand" : "border-border-strong",
        )}
      />
    </label>
  );
}

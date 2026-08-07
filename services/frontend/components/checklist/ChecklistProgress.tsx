import { estimateCompletionDate } from "@/lib/checklist-estimate";
import type { ChecklistItem } from "@/app/types/checklist";

// "Blocked" items don't exist in the backend schema (see ChecklistItemRow), so
// "remaining" here means unchecked, not unchecked-and-unblocked.
export default function ChecklistProgress({ items }: { items: ChecklistItem[] }) {
  const total = items.length;
  const done = items.filter((item) => item.checked).length;
  const remaining = total - done;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  const estimatedDate = estimateCompletionDate(remaining);

  return (
    <div
      data-testid="checklist-progress"
      className="rounded-2xl border border-border bg-surface p-4"
    >
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-brand-fg">
          {done} of {total} tasks complete
        </span>
        <span className="text-fg-subtle">{percent}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-canvas-inset">
        <div
          className="h-full rounded-full bg-success transition-all"
          style={{ width: `${percent}%` }}
        />
      </div>
      {estimatedDate && (
        <p className="mt-3 text-xs text-fg-subtle">
          Estimated completion:{" "}
          <span className="font-medium text-fg-muted">
            {estimatedDate.toLocaleDateString(undefined, {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </span>{" "}
          (approximate — assumes a few days per remaining task)
        </p>
      )}
    </div>
  );
}

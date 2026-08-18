import type { ReactNode } from "react";
import { estimateCompletionDate } from "@/lib/checklist-estimate";
import type { ChecklistItem } from "@/app/types/checklist";
import { Card, Progress, Text } from "@/components/ui";

// "Blocked" items don't exist in the backend schema (see ChecklistItemRow), so
// "remaining" here means unchecked, not unchecked-and-unblocked.
export default function ChecklistProgress({
  items,
  action,
}: {
  items: ChecklistItem[];
  action?: ReactNode;
}) {
  const total = items.length;
  const done = items.filter((item) => item.checked).length;
  const remaining = total - done;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  const estimatedDate = estimateCompletionDate(remaining);

  return (
    <Card
      data-testid="checklist-progress"
      padding="md"
      className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0 flex-1">
        <Progress
          value={done}
          max={Math.max(total, 1)}
          tone="success"
          size="md"
          label="Application progress"
          valueText={`${done} of ${total} tasks complete · ${percent}%`}
          showValue
        />
        {estimatedDate && (
          <Text size="sm" tone="subtle" className="mt-3">
            Estimated completion:{" "}
            <span className="font-medium text-fg-muted">
              {estimatedDate.toLocaleDateString(undefined, {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>{" "}
            · Approximate, based on the remaining tasks
          </Text>
        )}
      </div>
      {action && <div className="print-hidden shrink-0">{action}</div>}
    </Card>
  );
}

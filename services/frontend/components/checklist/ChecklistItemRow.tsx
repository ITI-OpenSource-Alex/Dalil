"use client";

import Checkbox from "@/components/ui/checkbox";
import type { ChecklistItem } from "@/app/types/checklist";

// No lock icon / "blocked" state here: GOA-084's ChecklistItem carries no
// blocked/blockedReason field, and fabricating one on the frontend would show a
// reason that was never actually computed. That AC is isolated pending a schema
// change owned by the checklist backend, not rebuilt here.
export default function ChecklistItemRow({
  item,
  onToggle,
}: {
  item: ChecklistItem;
  onToggle: (checked: boolean) => void;
}) {
  return (
    <li
      data-testid="checklist-item"
      data-checked={item.checked}
      className="flex items-start gap-3 rounded-xl border border-border bg-surface p-3"
    >
      <div className="pt-0.5">
        <Checkbox checked={item.checked} onChange={onToggle} label={item.title} />
      </div>
      <div className="min-w-0">
        <p
          className={`text-sm font-medium text-brand-fg ${item.checked ? "line-through text-fg-subtle" : ""}`}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="mt-0.5 text-xs text-fg-muted">{item.description}</p>
        )}
      </div>
    </li>
  );
}

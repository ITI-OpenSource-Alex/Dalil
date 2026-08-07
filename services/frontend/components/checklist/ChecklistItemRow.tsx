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
      className="flex items-start gap-3 rounded-xl border border-[#E4EAE4] bg-white p-3"
    >
      <div className="pt-0.5">
        <Checkbox checked={item.checked} onChange={onToggle} label={item.title} />
      </div>
      <div className="min-w-0">
        <p
          className={`text-sm font-medium text-[#0D3820] ${item.checked ? "line-through text-[#899C8B]" : ""}`}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="mt-0.5 text-xs text-[#526053]">{item.description}</p>
        )}
      </div>
    </li>
  );
}

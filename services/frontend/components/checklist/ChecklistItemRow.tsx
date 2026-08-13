"use client";

import Checkbox from "@/components/ui/checkbox";
import type { ChecklistItem } from "@/app/types/checklist";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

// No lock icon / "blocked" state here: GOA-084's ChecklistItem carries no
// blocked/blockedReason field, and fabricating one on the frontend would show a
// reason that was never actually computed. That AC is isolated pending a schema
// change owned by the checklist backend, not rebuilt here.
export default function ChecklistItemRow({
  item,
  onToggle,
  programId,
  programName,
  phase,
}: {
  item: ChecklistItem;
  onToggle: (checked: boolean) => void;
  programId?: string;
  programName?: string;
  phase?: string;
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
      <div className="min-w-0 flex-1">
        <p
          className={`text-sm font-medium text-brand-fg ${item.checked ? "line-through text-fg-subtle" : ""}`}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="mt-0.5 text-xs text-fg-muted">{item.description}</p>
        )}
      </div>
      <ExplainWithDalilButton
        context={{
          kind: "checklist",
          title: `${item.title} checklist item`,
          subjectId: programId ? `${programId}:${item.itemId}` : item.itemId,
          summary: programName && phase ? `${programName} · ${phase}` : programName ?? phase,
          facts: compactFacts([
            fact("Checklist item", item.title),
            fact("Description", item.description),
            fact("Phase", phase),
            fact("Category", item.category),
            fact("Completion status", item.checked ? "Completed" : "Not completed"),
            fact("Programme", programName),
          ]),
          limitations: [
            "Checklist items are planning guidance; the programme's official instructions remain authoritative.",
          ],
        }}
        prompt={`Why is “${item.title}” on my ${programName ?? "programme"} checklist? Explain what it is, when I need it, and how I can verify it.`}
      />
    </li>
  );
}

"use client";

import Checkbox from "@/components/ui/checkbox";
import Link from "next/link";
import type { ChecklistItem } from "@/app/types/checklist";
import { MOTIVATION_LETTER_ACTION } from "@/app/types/checklist";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";
import { Button, Text } from "@/components/ui";

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
      className="flex items-start gap-3 bg-surface p-4 transition-colors hover:bg-canvas-subtle"
    >
      <div className="pt-0.5">
        <Checkbox checked={item.checked} onChange={onToggle} label={item.title} />
      </div>
      <div className="min-w-0 flex-1">
        <Text
          size="sm"
          weight="semibold"
          className={`text-sm font-medium text-brand-fg ${item.checked ? "line-through text-fg-subtle" : ""}`}
        >
          {item.title}
        </Text>
        {item.description && (
          <Text size="sm" tone="muted" className="mt-1" measure>
            {item.description}
          </Text>
        )}
        {/* An actionable item keeps its checkbox: the review drives the tick, but a
            student who drafted their letter elsewhere can still mark it done. */}
        {item.actionType === MOTIVATION_LETTER_ACTION && (item.actionTarget || programId) && (
          <Button variant="outline" size="sm" asChild className="mt-3">
            <Link
              data-testid="motivation-letter-cta"
              href={`/checklist/${encodeURIComponent(item.actionTarget ?? programId ?? "")}/motivation-letter`}
            >
              Review my letter <span aria-hidden="true">&rarr;</span>
            </Link>
          </Button>
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

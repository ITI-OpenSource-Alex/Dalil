"use client";

import { useChecklist } from "@/app/hooks/useChecklist";
import { phaseForItem } from "@/lib/checklist-phases";
import type { ChecklistItem, Phase } from "@/app/types/checklist";
import PhaseSection from "./PhaseSection";
import FinancialRequirements from "./FinancialRequirements";
import ChecklistProgress from "./ChecklistProgress";
import PrintButton from "./PrintButton";

const GENERATED_PHASES: Exclude<Phase, "Financial Requirements">[] = [
  "Language Prep",
  "Documents",
  "Application",
  "Post-acceptance",
];

function groupByPhase(items: ChecklistItem[]) {
  const groups = new Map<string, ChecklistItem[]>();
  for (const item of items) {
    const phase = phaseForItem(item.category, item.itemId);
    groups.set(phase, [...(groups.get(phase) ?? []), item]);
  }
  return groups;
}

export default function ChecklistView({ programId }: { programId: string }) {
  const { checklist, financialItems, status, error, toggleError, retry, toggleItem } =
    useChecklist(programId);

  if (status === "loading" || status === "idle") {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading checklist">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 w-full animate-pulse rounded-2xl bg-gray-100" />
        ))}
      </div>
    );
  }

  if (status === "error" || !checklist) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 p-6 text-center">
        <p className="text-sm text-red-700">{error}</p>
        <button
          type="button"
          onClick={retry}
          className="mt-3 rounded-full bg-red-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  const grouped = groupByPhase(checklist.items);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <ChecklistProgress items={checklist.items} />
        <div className="pl-4">
          <PrintButton />
        </div>
      </div>

      {toggleError && (
        <p className="print-hidden text-xs text-red-600">{toggleError}</p>
      )}

      {GENERATED_PHASES.map((phase) => (
        <PhaseSection
          key={phase}
          phase={phase}
          items={grouped.get(phase) ?? []}
          onToggle={toggleItem}
        />
      ))}

      {/* Financial Requirements is rendered from a separate, structured-only
          source (financialItems), never from the LLM-generated checklist items
          above — see FinancialRequirements.tsx. */}
      <FinancialRequirements items={financialItems} />
    </div>
  );
}

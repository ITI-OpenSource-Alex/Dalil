"use client";

import { useEffect } from "react";
import { useChecklist } from "@/app/hooks/useChecklist";
import { rememberChecklist } from "@/lib/checklist-index";
import { phaseForItem } from "@/lib/checklist-phases";
import type { ChecklistItem, Phase } from "@/app/types/checklist";
import PhaseSection from "./PhaseSection";
import FinancialRequirements from "./FinancialRequirements";
import ChecklistProgress from "./ChecklistProgress";
import PrintButton from "./PrintButton";
import { Alert, Button, Skeleton } from "@/components/ui";

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

export default function ChecklistView({
  programId,
  programName,
  university,
  country,
}: {
  programId: string;
  /** Programme metadata for the /checklists index, when the caller knows it. */
  programName?: string;
  university?: string | null;
  country?: string | null;
}) {
  const { checklist, financialItems, status, error, toggleError, retry, toggleItem } =
    useChecklist(programId);

  // Records this checklist (and its live progress) in the local index that
  // backs /checklists -- see lib/checklist-index.ts for why that page cannot
  // simply ask the backend for a list. Re-runs on every toggle, so the
  // percentage shown on the index is never stale by more than a page visit.
  const items = checklist?.items;
  useEffect(() => {
    if (!items) return;
    rememberChecklist({
      programId,
      programName: programName || programId,
      university: university ?? null,
      country: country ?? null,
      totalItems: items.length,
      completedItems: items.filter((item) => item.checked).length,
    });
  }, [items, programId, programName, university, country]);

  if (status === "loading" || status === "idle") {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Loading checklist">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} shape="block" className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (status === "error" || !checklist) {
    return (
      <Alert
        tone="danger"
        actions={
          <Button variant="danger" size="sm" onClick={retry}>
            Retry
          </Button>
        }
      >
        {error}
      </Alert>
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
        <Alert tone="danger" className="print-hidden">
          {toggleError}
        </Alert>
      )}

      {GENERATED_PHASES.map((phase) => (
        <PhaseSection
          key={phase}
          phase={phase}
          items={grouped.get(phase) ?? []}
          onToggle={toggleItem}
          programId={programId}
          programName={programName}
        />
      ))}

      {/* Financial Requirements is rendered from a separate, structured-only
          source (financialItems), never from the LLM-generated checklist items
          above — see FinancialRequirements.tsx. */}
      <FinancialRequirements
        items={financialItems}
        programId={programId}
        programName={programName}
      />
    </div>
  );
}

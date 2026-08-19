"use client";

import { useEffect } from "react";
import { useChecklist } from "@/app/hooks/useChecklist";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { rememberChecklist } from "@/lib/checklist-index";
import { phaseForItem } from "@/lib/checklist-phases";
import type { ChecklistItem, Phase } from "@/app/types/checklist";
import PhaseSection from "./PhaseSection";
import FinancialRequirements from "./FinancialRequirements";
import ChecklistProgress from "./ChecklistProgress";
import PrintButton from "./PrintButton";
import ProgramCvRecommendations from "./ProgramCvRecommendations";
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
  const { user } = useCurrentUser();
  const userId = user?.id;
  const { checklist, financialItems, status, error, toggleError, retry, toggleItem } =
    useChecklist(programId);

  // Records this checklist (and its live progress) in the local index that
  // backs /checklists -- see lib/checklist-index.ts for why that page cannot
  // simply ask the backend for a list. Re-runs on every toggle, so the
  // percentage shown on the index is never stale by more than a page visit.
  const items = checklist?.items;
  useEffect(() => {
    if (!items) return;
    rememberChecklist(
      {
        programId,
        programName: checklist?.programName || programName || programId,
        university: university ?? null,
        country: checklist?.country || country || null,
        totalItems: items.length,
        completedItems: items.filter((item) => item.checked).length,
      },
      userId,
    );
  }, [items, checklist?.programName, checklist?.country, programId, programName, university, country, userId]);

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
  const resolvedProgramName = checklist.programName || programName || programId;
  const resolvedCountry = checklist.country || country;

  // CSS Grid rows share the height of their tallest card. That left a large
  // hole below a one-item phase whenever the phase beside it contained six or
  // seven items. Build two independent vertical tracks instead, assigning the
  // next card to the lighter track. The weight is intentionally simple and
  // deterministic; it only needs to approximate rendered card height.
  const layoutSections: Array<
    | {
        kind: "phase";
        key: string;
        phase: Exclude<Phase, "Financial Requirements">;
        items: ChecklistItem[];
        weight: number;
      }
    | { kind: "financial"; key: string; weight: number }
  > = GENERATED_PHASES.map((phase) => ({
    kind: "phase" as const,
    key: phase,
    phase,
    items: grouped.get(phase) ?? [],
    weight: 2 + (grouped.get(phase)?.length ?? 0),
  })).filter((section) => section.items.length > 0);

  if (financialItems.length > 0) {
    layoutSections.push({
      kind: "financial",
      key: "Financial Requirements",
      // Financial rows carry sources and verification metadata, so each is
      // usually taller than a generated checklist row.
      weight: 2 + financialItems.length * 2,
    });
  }

  const sectionColumns = [[], []] as Array<typeof layoutSections>;
  const columnWeights = [0, 0];
  for (const section of layoutSections) {
    const column = columnWeights[0] <= columnWeights[1] ? 0 : 1;
    sectionColumns[column].push(section);
    columnWeights[column] += section.weight;
  }

  return (
    <div className="space-y-8">
      <ChecklistProgress
        items={checklist.items}
        action={<PrintButton />}
      />

      {toggleError && (
        <Alert tone="danger" className="print-hidden">
          {toggleError}
        </Alert>
      )}

      <ProgramCvRecommendations
        programId={programId}
        programName={resolvedProgramName}
        country={resolvedCountry}
      />

      <div className="grid items-start gap-6 lg:grid-cols-2">
        {sectionColumns.map((sections, columnIndex) => (
          <div key={columnIndex} className="space-y-6">
            {sections.map((section) =>
              section.kind === "phase" ? (
                <PhaseSection
                  key={section.key}
                  phase={section.phase}
                  items={section.items}
                  onToggle={toggleItem}
                  programId={programId}
                  programName={resolvedProgramName}
                />
              ) : (
                /* Financial Requirements remains a separate, structured-only
                   source and is never mixed into generated checklist items. */
                <FinancialRequirements
                  key={section.key}
                  items={financialItems}
                  programId={programId}
                  programName={resolvedProgramName}
                />
              ),
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

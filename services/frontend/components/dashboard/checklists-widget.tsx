"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ListChecks } from "lucide-react";
import ChecklistProgress from "@/components/checklist/ChecklistProgress";
import {
  checklistSubtitle,
  isPlaceholderProgramName,
  readChecklistIndex,
  rememberChecklist,
  type ChecklistIndexEntry,
} from "@/lib/checklist-index";
import { getOpportunity } from "@/lib/opportunities-api";
import { Button, Card, Icon, Text } from "@/components/ui";

function useResolvedEntry(entry: ChecklistIndexEntry | undefined) {
  const [resolved, setResolved] = useState<ChecklistIndexEntry | undefined>(
    entry,
  );

  useEffect(() => {
    if (!entry) {
      setResolved(undefined);
      return;
    }

    const needsLookup =
      isPlaceholderProgramName(entry.programName, entry.programId) ||
      !entry.university ||
      !entry.country;

    if (!needsLookup) {
      setResolved(entry);
      return;
    }

    let cancelled = false;
    void getOpportunity(entry.programId)
      .then((program) => {
        if (cancelled) return;
        const enriched: ChecklistIndexEntry = {
          ...entry,
          programName: program.programName,
          university: program.university,
          country: program.country,
        };
        setResolved(enriched);
        rememberChecklist({
          programId: entry.programId,
          programName: program.programName,
          university: program.university,
          country: program.country,
          totalItems: entry.totalItems,
          completedItems: entry.completedItems,
        });
      })
      .catch(() => {
        if (!cancelled) setResolved(entry);
      });

    return () => {
      cancelled = true;
    };
  }, [entry]);

  return resolved;
}

export function ChecklistsWidget() {
  const [entries, setEntries] = useState<ChecklistIndexEntry[]>([]);
  useEffect(() => setEntries(readChecklistIndex()), []);
  const next = entries[0];
  const display = useResolvedEntry(next);

  return (
    <Card data-testid="dashboard-checklists">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon icon={ListChecks} size="sm" className="text-brand-fg" />
          <Text className="font-semibold">Application checklists</Text>
        </div>
        <Button size="sm" variant="ghost" trailingIcon={ArrowRight} asChild>
          <Link href="/checklists">View all</Link>
        </Button>
      </div>
      {display ? (
        <div className="mt-4 space-y-3">
          <div>
            <Link
              href={`/checklist/${encodeURIComponent(display.programId)}`}
              className="font-medium text-fg hover:text-brand-fg"
            >
              {display.programName}
            </Link>
            <Text size="sm" tone="muted" className="mt-0.5 truncate">
              {checklistSubtitle(display)}
            </Text>
          </div>
          {display.totalItems > 0 ? (
            <ChecklistProgress
              summary={{
                completed: display.completedItems,
                total: display.totalItems,
              }}
            />
          ) : (
            <Text size="sm" tone="subtle">
              Open to generate your step-by-step plan.
            </Text>
          )}
        </div>
      ) : (
        <div className="mt-4">
          <Text size="sm" tone="muted">
            Build a programme-specific list of required papers and profile gaps.
          </Text>
          <Button size="sm" className="mt-3" asChild>
            <Link href="/checklists">Create a checklist</Link>
          </Button>
        </div>
      )}
    </Card>
  );
}

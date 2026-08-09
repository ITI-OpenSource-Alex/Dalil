"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ListChecks } from "lucide-react";
import {
  readChecklistIndex,
  type ChecklistIndexEntry,
} from "@/lib/checklist-index";
import { Button, Card, Icon, Progress, Text } from "@/components/ui";

export function ChecklistsWidget() {
  const [entries, setEntries] = useState<ChecklistIndexEntry[]>([]);
  useEffect(() => setEntries(readChecklistIndex()), []);
  const next = entries[0];

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
      {next ? (
        <div className="mt-4">
          <Link
            href={`/checklist/${encodeURIComponent(next.programId)}`}
            className="font-medium text-fg hover:text-brand-fg"
          >
            {next.programName}
          </Link>
          <Progress
            className="mt-2"
            value={next.completedItems}
            max={Math.max(1, next.totalItems)}
            label={`${next.programName} checklist progress`}
            valueText={`${next.completedItems} of ${next.totalItems}`}
          />
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

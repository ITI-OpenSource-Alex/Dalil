"use client";

import type { ExamProgress } from "@/lib/exam-api";
import { estimateOverallPracticeBand } from "@/lib/exam-progress";
import { formatBand } from "@/lib/ielts";
import { Heading, Text } from "@/components/ui";

export function EstimatedOverallBand({ progress }: { progress: ExamProgress }) {
  const band = estimateOverallPracticeBand(progress);
  if (band === null) return null;

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <Heading as="h3" size="xs" className="text-fg-muted">
        Estimated overall IELTS band
      </Heading>
      <p className="mt-1 text-3xl font-semibold text-fg">{formatBand(band)}</p>
      <Text size="sm" tone="muted" className="mt-1">
        based on practice exams
      </Text>
    </div>
  );
}

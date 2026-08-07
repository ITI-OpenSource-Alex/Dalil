"use client";

import type { ExamType } from "@/app/types/exam";
import type { NormalizedWritingTask } from "@/lib/normalizeWritingTasks";

interface StimulusPanelProps {
  task: NormalizedWritingTask;
  examType: ExamType;
}

/**
 * The material a task is written about, shown above the textarea.
 *
 * The two IELTS variants present different material, and this component is the
 * one place that difference lives:
 *
 *   Academic Task 1 — describes a chart/graph/diagram. Today only the prompt
 *     text is available (see the TODO below), so that is what renders.
 *   General Training Task 1 — a letter scenario, which is prose by nature and
 *     never had an image.
 *   Task 2 (both variants) — an essay question. Prompt only.
 *
 * ── Why there is no image here ────────────────────────────────────────────
 * TODO(GOA-058 follow-up): reintroduce the Academic Task 1 stimulus image.
 * The original requirement was an S3 pre-signed URL rendered with next/image
 * plus a zoom control. It is postponed because the Writing agents changed and
 * the current pipeline no longer supports image-based evaluation — end to end,
 * nothing produces an image: ingestion extracts none, none is uploaded to S3,
 * nothing pre-signs one, and the session API exposes no such field.
 *
 * When that pipeline lands, the change is additive and local to this file:
 *   1. add `stimulusImageUrl?: string` to NormalizedWritingTask and populate it
 *      in lib/normalizeWritingTasks.ts (task 1 only);
 *   2. render it here, below the prompt, behind `isAcademic && stimulusImageUrl`:
 *        <Image src={url} alt="Task 1 stimulus" width={1200} height={800}
 *               unoptimized className="h-auto w-full rounded-lg object-contain" />
 *      `unoptimized` matters — a pre-signed URL expires and carries per-request
 *      credentials in its query string, so Next's image optimizer must not
 *      cache or re-key it;
 *   3. add the zoom button + modal (an overlay with Escape-to-close).
 *
 * Nothing else needs to move: the Academic/General branch, the props and the
 * call site in WritingTaskPanel all stay exactly as they are. `examType` is
 * kept as a prop for that reason — it is what selects the Academic variant.
 * ──────────────────────────────────────────────────────────────────────────
 */
export default function StimulusPanel({ task, examType }: StimulusPanelProps) {
  const isAcademic = examType === "Academic";

  // Test ids are task-scoped because both tab panels stay mounted (the inactive
  // one is hidden, not unmounted, so drafts survive a tab switch) — an unscoped
  // id would match twice.
  const testId = (name: string) => `${name}-${task.taskNumber}`;

  return (
    <div className="mb-4" data-testid={testId("stimulus-panel")}>
      <div
        className="mb-3 text-sm text-fg-muted whitespace-pre-wrap leading-relaxed"
        data-testid={testId(
          isAcademic ? "stimulus-prompt" : "stimulus-scenario-text",
        )}
      >
        {task.prompt}
      </div>

      {task.instructions && (
        <p className="mb-3 text-xs font-medium text-fg-subtle">
          {task.instructions}
        </p>
      )}
    </div>
  );
}

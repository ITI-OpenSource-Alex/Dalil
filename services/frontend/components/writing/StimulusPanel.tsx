"use client";

import { useState } from "react";
import Image from "next/image";
import { ZoomIn } from "lucide-react";
import type { ExamType } from "@/app/types/exam";
import type { NormalizedWritingTask } from "@/lib/normalizeWritingTasks";
import { Icon, Modal, ModalContent, ModalTrigger } from "@/components/ui";

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
 *   Academic Task 1 — describes a chart/graph/diagram. The chart is delivered
 *     as a pre-signed S3 URL on the session payload (see normalizeWritingTasks)
 *     and rendered below the prompt with a zoom control, because the fine
 *     detail of a chart matters and the inline size is deliberately narrow.
 *   General Training Task 1 — a letter scenario, which is prose by nature and
 *     never had an image.
 *   Task 2 (both variants) — an essay question. Prompt only.
 *
 * `stimulusImageUrl` is rendered with `next/image` in `unoptimized` mode: the
 * URL is pre-signed and expires, and carries per-request credentials in its
 * query string, so Next's image optimizer must not cache or re-key it. The
 * image only appears for Academic Task 1 and only when the payload actually
 * carried one — General Training, Task 2, and any session with no chart render
 * prompt-only exactly as before, so `examType` still selects the variant.
 */
export default function StimulusPanel({ task, examType }: StimulusPanelProps) {
  const isAcademic = examType === "Academic";
  const [zoomOpen, setZoomOpen] = useState(false);

  // Test ids are task-scoped because both tab panels stay mounted (the inactive
  // one is hidden, not unmounted, so drafts survive a tab switch) — an unscoped
  // id would match twice.
  const testId = (name: string) => `${name}-${task.taskNumber}`;

  const showImage = isAcademic && Boolean(task.stimulusImageUrl);

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

      {showImage && (
        <Modal open={zoomOpen} onOpenChange={setZoomOpen}>
          <figure className="relative mb-3 overflow-hidden rounded-lg border border-border bg-surface">
            {/*
              unoptimized: the src is a pre-signed, expiring URL with credentials
              in its query string — Next's optimizer must neither cache nor
              re-key it. width/height are the intrinsic hint next/image needs;
              the classes let it scale responsively to the panel.
            */}
            <Image
              src={task.stimulusImageUrl as string}
              alt="Task 1 stimulus chart"
              width={1200}
              height={800}
              unoptimized
              data-testid={testId("stimulus-image")}
              className="h-auto w-full object-contain"
            />

            <ModalTrigger asChild>
              <button
                type="button"
                data-testid={testId("stimulus-zoom-button")}
                aria-label="Zoom into the Task 1 chart"
                className="absolute right-2 top-2 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/90 px-3 py-1.5 text-xs font-semibold text-fg-muted shadow-2xs backdrop-blur-sm transition hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
              >
                <Icon icon={ZoomIn} size="sm" />
                Zoom
              </button>
            </ModalTrigger>
          </figure>

          {/* Escape-to-close and focus handling come from the Radix dialog the
              Modal wraps; dismissible defaults to true. */}
          <ModalContent
            title="Task 1 stimulus chart"
            titleHidden
            size="xl"
            data-testid={testId("stimulus-zoom-modal")}
          >
            <Image
              src={task.stimulusImageUrl as string}
              alt="Task 1 stimulus chart, enlarged"
              width={1600}
              height={1200}
              unoptimized
              className="h-auto w-full object-contain"
            />
          </ModalContent>
        </Modal>
      )}
    </div>
  );
}

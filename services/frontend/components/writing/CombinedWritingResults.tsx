"use client";

import Link from "next/link";
import TaskResultCard from "@/components/writing/TaskResultCard";
import {
  formatBand,
  formatWeightedFormula,
  TASK_WEIGHT_PERCENT,
} from "@/lib/writing-exam";
import type { WritingResultResponse, WritingTaskResult } from "@/lib/exam-api";

interface CombinedWritingResultsProps {
  result: WritingResultResponse;
}

function taskBand(task: WritingTaskResult | undefined): number {
  return task?.evaluation?.overall_band ?? 0;
}

/**
 * The finished Writing paper: both tasks side by side and the weighted band.
 *
 * The overall band shown is the exam service's own `overall_band`, never a
 * client-side recomputation. The service already applies the marking rule
 * (`round((t1 + 2*t2) / 3 * 2) / 2`) and persists that value against the
 * session; recomputing it here would create a second implementation of a
 * marking rule, and the day the two drift a candidate is shown arithmetic that
 * does not add up. The formula string exists to *explain* the number, not to
 * produce it.
 */
export default function CombinedWritingResults({
  result,
}: CombinedWritingResultsProps) {
  const task1 = result.tasks?.["1"];
  const task2 = result.tasks?.["2"];

  const band1 = taskBand(task1);
  const band2 = taskBand(task2);

  return (
    <div data-testid="writing-combined-results" className="space-y-8">
      <div className="flex flex-col gap-4 rounded-3xl border border-border bg-surface p-8 shadow-2xs sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <span className="rounded-full border border-brand-border bg-brand-subtle px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-brand-fg">
            Official Simulation Result
          </span>
          <h2 className="mt-2 font-serif text-2xl text-fg md:text-3xl">
            Writing Analytics
          </h2>
          <p className="text-xs text-fg-subtle">
            Task 2 carries twice the weight of Task 1.
          </p>
        </div>

        <div className="shrink-0 rounded-2xl border border-border bg-canvas-subtle px-8 py-4 text-center">
          <p className="text-[10px] font-bold uppercase tracking-widest text-fg-subtle">
            Overall Band
          </p>
          <p
            data-testid="writing-overall-band"
            className="font-serif text-5xl font-bold text-brand-fg"
          >
            {formatBand(result.overall_band)}
          </p>
        </div>
      </div>

      <section className="rounded-2xl border border-border bg-surface p-6 shadow-2xs">
        <h3 className="mb-3 text-sm font-bold uppercase tracking-wide text-fg-subtle">
          How this band was calculated
        </h3>

        <p
          data-testid="writing-weighting-formula"
          className="font-mono text-sm leading-relaxed text-fg-muted"
        >
          {formatWeightedFormula(band1, band2, result.overall_band)}
        </p>

        <div className="mt-4 flex gap-2 text-[11px] font-semibold">
          <span className="rounded-full bg-canvas-subtle px-2.5 py-1 text-fg-muted">
            Task 1 · {TASK_WEIGHT_PERCENT[1]}%
          </span>
          <span className="rounded-full bg-canvas-subtle px-2.5 py-1 text-fg-muted">
            Task 2 · {TASK_WEIGHT_PERCENT[2]}%
          </span>
        </div>
      </section>

      <section>
        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-fg-subtle">
          Per-task breakdown
        </h3>

        {/*
          Side by side on desktop, stacked on narrow screens. Both are expanded
          here by default — unlike during the exam, where a collapsed card keeps
          the candidate focused on the task they are still writing, there is
          nothing left to protect their attention from once the paper is done.
        */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {([1, 2] as const).map((taskNumber) => {
            const task = taskNumber === 1 ? task1 : task2;

            if (!task) {
              return (
                <div
                  key={taskNumber}
                  data-testid={`writing-result-task-${taskNumber}-missing`}
                  className="rounded-2xl border border-dashed border-border bg-surface p-6 text-center text-xs text-fg-subtle"
                >
                  No Task {taskNumber} response was recorded.
                </div>
              );
            }

            return (
              <TaskResultCard
                key={taskNumber}
                taskNumber={taskNumber}
                overallBand={taskBand(task)}
                wordCount={task.word_count}
                penaltyFlag={task.penalty_flag}
                evaluations={task.evaluation?.evaluations ?? []}
                essayText={task.response_text}
                defaultExpanded
              />
            );
          })}
        </div>
      </section>

      <div className="border-t border-border pt-6">
        <Link
          href="/exam"
          className="inline-block rounded-full bg-brand px-5 py-2.5 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          Return to Skills Workspace
        </Link>
      </div>
    </div>
  );
}

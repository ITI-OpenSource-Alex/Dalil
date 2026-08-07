"use client";

import { AlertTriangle, Clock, Loader2 } from "lucide-react";
import type { ExamType } from "@/app/types/exam";
import StimulusPanel from "@/components/writing/StimulusPanel";
import type { NormalizedWritingTask } from "@/lib/normalizeWritingTasks";
import {
  countWords,
  isUnderMinimum,
  TASK_SUGGESTED_MINUTES,
  TASK_WORD_TARGETS,
  UNDER_MINIMUM_WARNING,
  wordCountState,
  type WritingTaskNumber,
} from "@/lib/writing-exam";

export type TaskSubmitStatus = "idle" | "submitting" | "error";

interface WritingTaskPanelProps {
  taskNumber: WritingTaskNumber;
  task: NormalizedWritingTask | undefined;
  examType: ExamType;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  status: TaskSubmitStatus;
  errorMessage?: string;
  /** Minutes since the exam started, for the recommended-time indicator. */
  elapsedMinutes: number;
}

/**
 * The editor for one task: what to write about, somewhere to write it, and live
 * feedback on length and pacing.
 *
 * Rendering is driven entirely by props — this component owns no draft state.
 * The drafts live one level up in WritingExam so that switching tabs cannot
 * unmount a half-written response, which is what "Task 2 remains fully editable
 * while Task 1 evaluation runs" ultimately depends on.
 */
export default function WritingTaskPanel({
  taskNumber,
  task,
  examType,
  value,
  onChange,
  onSubmit,
  status,
  errorMessage,
  elapsedMinutes,
}: WritingTaskPanelProps) {
  const wordCount = countWords(value);
  const target = TASK_WORD_TARGETS[taskNumber];
  const met = wordCountState(wordCount, taskNumber) === "met";
  const underMinimum = isUnderMinimum(wordCount, taskNumber);
  const suggestedMinutes = TASK_SUGGESTED_MINUTES[taskNumber];
  const submitting = status === "submitting";

  // Task 1's 20 minutes are the first 20 of the hour; Task 2's 40 follow it.
  const budgetStart = taskNumber === 1 ? 0 : TASK_SUGGESTED_MINUTES[1];
  const overSuggestedTime = elapsedMinutes > budgetStart + suggestedMinutes;

  if (!task) {
    return (
      <div
        data-testid={`task-${taskNumber}-missing`}
        className="rounded-2xl border border-dashed border-border bg-surface p-8 text-center text-xs text-fg-subtle"
      >
        No Task {taskNumber} prompt was found for this exam paper.
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-border bg-surface p-5 shadow-2xs">
      <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-2">
        <h4 className="font-serif text-sm font-bold text-fg">
          Task {taskNumber}
        </h4>

        <span
          data-testid={`task-${taskNumber}-suggested-time`}
          className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
            overSuggestedTime
              ? "bg-warning-subtle text-warning-fg"
              : "bg-canvas-subtle text-fg-muted"
          }`}
        >
          <Clock size={12} aria-hidden="true" />
          Suggested: {suggestedMinutes} min for Task {taskNumber}
        </span>
      </div>

      <StimulusPanel task={task} examType={examType} />

      {/*
        A plain textarea, deliberately. Real IELTS offers no formatting, and rich
        text would also corrupt the character offsets the inline feedback relies
        on — those are computed against the raw submitted string.
      */}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={submitting}
        data-testid={`task-${taskNumber}-textarea`}
        aria-label={`Task ${taskNumber} response`}
        placeholder={`Compose your Task ${taskNumber} response here...`}
        className="w-full flex-1 resize-none rounded-xl border border-border bg-canvas-subtle p-3.5 text-sm text-fg-muted transition focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand-muted disabled:opacity-60"
      />

      {underMinimum && wordCount > 0 && (
        <div
          data-testid={`task-${taskNumber}-under-minimum-warning`}
          className="mt-3 flex items-start gap-2 rounded-xl border border-warning-border bg-warning-subtle px-3 py-2 text-xs text-warning-fg"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{UNDER_MINIMUM_WARNING}</span>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-3">
        <span
          data-testid={`task-${taskNumber}-word-counter`}
          data-state={met ? "met" : "below"}
          className={`text-xs font-semibold tabular-nums ${
            met ? "text-success-fg" : "text-warning-fg"
          }`}
        >
          {wordCount} / {target} words
        </span>

        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting || wordCount === 0}
          data-testid={`task-${taskNumber}-submit`}
          className="flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          {submitting && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
          {submitting ? "Evaluating..." : `Submit Task ${taskNumber}`}
        </button>
      </div>

      {status === "error" && errorMessage && (
        <p
          data-testid={`task-${taskNumber}-error`}
          className="mt-2 text-xs text-danger"
          role="alert"
        >
          {errorMessage}
        </p>
      )}
    </div>
  );
}

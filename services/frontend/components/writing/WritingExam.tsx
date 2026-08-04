"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import type { ExamType } from "@/app/types/exam";
import {
  submitWritingTask,
  type ExamSessionResponse,
  type WritingCriterionEvaluation,
} from "@/lib/exam-api";
import {
  findWritingTask,
  normalizeWritingTasks,
} from "@/lib/normalizeWritingTasks";
import { elapsedMinutes as toElapsedMinutes } from "@/lib/writing-exam";
import TaskResultCard from "@/components/writing/TaskResultCard";
import WritingTaskPanel, {
  type TaskSubmitStatus,
} from "@/components/writing/WritingTaskPanel";

interface WritingExamProps {
  sessionId: string;
  session: ExamSessionResponse;
  examType: ExamType;
  /** From useExamTimer in the shell — used for the pacing indicator. */
  secondsLeft: number;
  /** Bumped by the shell when the exam clock expires. */
  forceSubmitSignal: number;
  onCompleted: () => void;
}

type TaskNumber = 1 | 2;

interface TaskOutcome {
  overallBand: number;
  wordCount: number;
  penaltyFlag: boolean;
  evaluations: WritingCriterionEvaluation[];
  essayText: string;
}

/**
 * The Writing exam: two tasks, submitted and evaluated independently.
 *
 * This component exists because the Writing exam is the only skill whose parts
 * are graded while the candidate is still working. The exam service grades Task
 * 1 the moment it lands and leaves the session `in_progress` so Task 2 stays
 * submittable, and this is the UI half of that contract.
 *
 * Two structural decisions follow directly from it, and neither is cosmetic:
 *
 *  1. Both drafts live here, above the tabs. Tabs render one task at a time, so
 *     if the drafts lived in the panels a tab switch would unmount a
 *     half-written response and lose it.
 *
 *  2. Submission status is per task and stays inside this component. The exam
 *     shell renders a full-screen "Analysing performance..." overlay whenever
 *     its own status is "evaluating"; letting Task 1's evaluation reach that
 *     state would put a blocking spinner over an exam the candidate is still
 *     sitting, which is exactly what GOA-058 forbids.
 */
export default function WritingExam({
  sessionId,
  session,
  examType,
  secondsLeft,
  forceSubmitSignal,
  onCompleted,
}: WritingExamProps) {
  const tasks = useMemo(
    () => normalizeWritingTasks(session.questions),
    [session.questions],
  );

  const [activeTask, setActiveTask] = useState<TaskNumber>(1);
  const [drafts, setDrafts] = useState<Record<TaskNumber, string>>({
    1: "",
    2: "",
  });
  const [status, setStatus] = useState<Record<TaskNumber, TaskSubmitStatus>>({
    1: "idle",
    2: "idle",
  });
  const [errors, setErrors] = useState<Record<TaskNumber, string | undefined>>({
    1: undefined,
    2: undefined,
  });
  const [outcomes, setOutcomes] = useState<
    Partial<Record<TaskNumber, TaskOutcome>>
  >({});

  const elapsed = toElapsedMinutes(session.time_limit_seconds, secondsLeft);

  const setTaskStatus = (task: TaskNumber, next: TaskSubmitStatus) =>
    setStatus((current) => ({ ...current, [task]: next }));

  /**
   * Submits one task and records its evaluation.
   *
   * Returns the submit status so the timer-expiry path can tell whether the
   * exam finished. Never throws: a failed task must leave the other one usable,
   * so the error is captured against the task that produced it.
   */
  const submitTask = useCallback(
    async (taskNumber: TaskNumber): Promise<"submitted" | "failed" | "empty"> => {
      const essayText = drafts[taskNumber];
      if (!essayText.trim()) return "empty";
      if (outcomes[taskNumber]) return "submitted";

      setTaskStatus(taskNumber, "submitting");
      setErrors((current) => ({ ...current, [taskNumber]: undefined }));

      try {
        const result = await submitWritingTask(
          sessionId,
          taskNumber,
          essayText,
        );

        setOutcomes((current) => ({
          ...current,
          [taskNumber]: {
            overallBand: result.overall_band,
            wordCount: result.word_count,
            penaltyFlag: result.penalty_flag,
            // Older backends omit this; an empty list degrades the card to a
            // band score rather than crashing the exam.
            evaluations: result.evaluations ?? [],
            // The submitted text, kept verbatim: inline highlight offsets are
            // computed server-side against this exact string.
            essayText,
          },
        }));
        setTaskStatus(taskNumber, "idle");

        return "submitted";
      } catch (error) {
        setTaskStatus(taskNumber, "error");
        setErrors((current) => ({
          ...current,
          [taskNumber]:
            error instanceof Error
              ? error.message
              : "Could not evaluate this task. Please try again.",
        }));
        return "failed";
      }
    },
    [drafts, outcomes, sessionId],
  );

  const handleSubmitTask = (taskNumber: TaskNumber) => {
    void (async () => {
      const result = await submitTask(taskNumber);
      // Moving the candidate to the task they still have to write is the useful
      // default; they can switch back to read the feedback whenever they want.
      if (result === "submitted" && taskNumber === 1 && !outcomes[2]) {
        setActiveTask(2);
      }
    })();
  };

  // Both tasks in ⇒ the session is scored and the combined result exists.
  const bothSubmitted = Boolean(outcomes[1] && outcomes[2]);

  useEffect(() => {
    if (bothSubmitted) onCompleted();
  }, [bothSubmitted, onCompleted]);

  /**
   * Time-up: submit whatever has been written that has not been submitted yet.
   *
   * Sequential rather than parallel — each call triggers four LLM evaluations
   * upstream, and firing both at once doubles the peak load for no gain when
   * the candidate is leaving anyway. Skipped on the initial render, when the
   * signal is still 0.
   */
  useEffect(() => {
    if (forceSubmitSignal === 0) return;

    void (async () => {
      for (const taskNumber of [1, 2] as const) {
        if (!outcomes[taskNumber]) {
          await submitTask(taskNumber);
        }
      }
      onCompleted();
    })();
    // Deliberately keyed only on the signal: this must fire once per expiry,
    // not every time a draft or an outcome changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceSubmitSignal]);

  const renderTask = (taskNumber: TaskNumber) => {
    const outcome = outcomes[taskNumber];

    if (outcome) {
      return (
        <TaskResultCard
          taskNumber={taskNumber}
          overallBand={outcome.overallBand}
          wordCount={outcome.wordCount}
          penaltyFlag={outcome.penaltyFlag}
          evaluations={outcome.evaluations}
          essayText={outcome.essayText}
        />
      );
    }

    return (
      <WritingTaskPanel
        taskNumber={taskNumber}
        task={findWritingTask(tasks, taskNumber)}
        examType={examType}
        value={drafts[taskNumber]}
        onChange={(value) =>
          setDrafts((current) => ({ ...current, [taskNumber]: value }))
        }
        onSubmit={() => handleSubmitTask(taskNumber)}
        status={status[taskNumber]}
        errorMessage={errors[taskNumber]}
        elapsedMinutes={elapsed}
      />
    );
  };

  return (
    <div className="mx-auto flex h-full min-h-150 w-full max-w-4xl flex-col">
      {/* Tabs follow components/reading/SectionTabs.tsx. */}
      <div
        role="tablist"
        aria-label="Writing tasks"
        className="mb-4 flex gap-1 border-b border-gray-200"
      >
        {([1, 2] as const).map((taskNumber) => {
          const active = taskNumber === activeTask;
          const done = Boolean(outcomes[taskNumber]);

          return (
            <button
              key={taskNumber}
              type="button"
              role="tab"
              aria-selected={active}
              data-testid={`writing-task-tab-${taskNumber}`}
              onClick={() => setActiveTask(taskNumber)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold transition ${
                active
                  ? "border-b-2 border-emerald-700 text-emerald-800"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {done && <CheckCircle2 size={13} className="text-emerald-600" />}
              Task {taskNumber}
            </button>
          );
        })}
      </div>

      {/*
        Both tasks stay mounted and the inactive one is hidden with CSS rather
        than unmounted. Conditional rendering would destroy the inactive
        textarea along with its draft, its scroll position and its selection
        every time the candidate glanced at the other tab.
      */}
      {([1, 2] as const).map((taskNumber) => (
        <div
          key={taskNumber}
          role="tabpanel"
          aria-label={`Task ${taskNumber}`}
          hidden={taskNumber !== activeTask}
          data-testid={`writing-task-panel-${taskNumber}`}
          className={
            taskNumber === activeTask ? "flex min-h-0 flex-1 flex-col" : "hidden"
          }
        >
          {renderTask(taskNumber)}
        </div>
      ))}
    </div>
  );
}

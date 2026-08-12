"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import EssayHighlighter from "@/components/chat/essay-highlighter";
import { CRITERION_COLOURS } from "@/components/chat/essay-highlighter";
import {
  formatBand,
  toEssayIssues,
  topIssuePerCriterion,
  UNDER_MINIMUM_WARNING,
  type WritingTaskNumber,
} from "@/lib/writing-exam";
import type { WritingCriterionEvaluation } from "@/lib/exam-api";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

interface TaskResultCardProps {
  taskNumber: WritingTaskNumber;
  overallBand: number;
  wordCount: number;
  penaltyFlag: boolean;
  evaluations: WritingCriterionEvaluation[];
  /** The response as submitted — highlight offsets are only valid against it. */
  essayText: string;
  /** Collapsed by default during the exam; results pages open it. */
  defaultExpanded?: boolean;
  subjectId?: string;
}

/**
 * A submitted task, collapsed into a compact feedback card.
 *
 * Collapsed-by-default is a deliberate exam-design choice, not a space saving.
 * Once Task 1 is in, the candidate's remaining time belongs to Task 2 — pulling
 * them into a detailed post-mortem is actively harmful. The headline band and
 * one issue per criterion are enough to course-correct; the full mark-up is one
 * click away for anyone who wants it.
 */
export default function TaskResultCard({
  taskNumber,
  overallBand,
  wordCount,
  penaltyFlag,
  evaluations,
  essayText,
  defaultExpanded = false,
  subjectId,
}: TaskResultCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const topIssues = topIssuePerCriterion(evaluations);
  const essayIssues = toEssayIssues(evaluations);

  return (
    <div
      data-testid={`task-${taskNumber}-result-card`}
      data-expanded={expanded}
      className="rounded-2xl border border-border bg-surface shadow-2xs"
    >
      <div className="flex items-center gap-1 pr-4">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          data-testid={`task-${taskNumber}-result-toggle`}
          className="flex min-w-0 flex-1 items-center justify-between gap-4 rounded-2xl p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          <div className="flex items-center gap-3">
            {expanded ? (
              <ChevronDown size={16} className="text-fg-subtle" aria-hidden="true" />
            ) : (
              <ChevronRight size={16} className="text-fg-subtle" aria-hidden="true" />
            )}
            <div>
              <h4 className="font-serif text-sm font-bold text-fg">
                Task {taskNumber} — evaluated
              </h4>
              <p className="text-xs text-fg-subtle">
                {wordCount} words · {expanded ? "Hide" : "Show"} full feedback
              </p>
            </div>
          </div>

          <div className="shrink-0 text-right">
            <p className="text-[10px] font-bold uppercase tracking-widest text-fg-subtle">
              Band
            </p>
            <p
              data-testid={`task-${taskNumber}-band`}
              className="font-serif text-2xl font-bold text-brand-fg"
            >
              {formatBand(overallBand)}
            </p>
          </div>
        </button>
        <ExplainWithDalilButton
          context={{
            kind: "writing_score",
            title: `Writing Task ${taskNumber} band ${formatBand(overallBand)}`,
            subjectId,
            facts: compactFacts([
              fact("Task", `Writing Task ${taskNumber}`),
              fact("Estimated band", formatBand(overallBand)),
              fact("Word count", wordCount),
              fact("Under-length penalty", penaltyFlag ? "Applied" : "Not applied"),
              ...evaluations.flatMap((evaluation) => [
                fact(`${evaluation.criterion} band`, formatBand(evaluation.band_score)),
                fact(`${evaluation.criterion} feedback`, evaluation.feedback),
                fact(`${evaluation.criterion} improvement`, evaluation.improvement_tip),
              ]),
            ]),
            limitations: [
              "This is an estimated practice score based on the submitted response, not an official IELTS result.",
            ],
          }}
          prompt={`Explain why my Writing Task ${taskNumber} response received band ${formatBand(overallBand)}. Which criterion limited it most, and what should I revise first?`}
        />
      </div>

      {/*
        The penalty is reported by the server (penalty_flag), not recomputed
        here, so the card can never contradict what was actually recorded
        against the submission.
      */}
      {penaltyFlag && (
        <div
          data-testid={`task-${taskNumber}-penalty-warning`}
          className="mx-5 mb-4 flex items-start gap-2 rounded-xl border border-warning-border bg-warning-subtle px-3 py-2 text-xs text-warning-fg"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{UNDER_MINIMUM_WARNING}</span>
        </div>
      )}

      {/* Collapsed view: the headline finding per criterion. */}
      <div className="grid grid-cols-1 gap-2 px-5 pb-5 sm:grid-cols-2">
        {topIssues.map((item) => {
          const colours = CRITERION_COLOURS[item.criterion];

          return (
            <div
              key={item.criterion}
              data-testid={`task-${taskNumber}-criterion-${item.criterion}`}
              className="rounded-xl border border-border bg-canvas-subtle p-3"
              style={{ borderLeft: `3px solid ${colours?.text ?? "var(--color-fg-muted)"}` }}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span
                  className="text-[10px] font-bold uppercase tracking-wide"
                  style={{ color: colours?.text ?? "var(--color-fg-muted)" }}
                >
                  {item.label}
                </span>
                <div className="flex items-center gap-1">
                  <span className="text-xs font-bold text-fg-muted">
                    {formatBand(item.band)}
                  </span>
                  <ExplainWithDalilButton
                    context={{
                      kind: "writing_score",
                      title: `Writing Task ${taskNumber} ${item.label} band ${formatBand(item.band)}`,
                      subjectId,
                      facts: compactFacts([
                        fact("Task", `Writing Task ${taskNumber}`),
                        fact("Criterion", item.label),
                        fact("Criterion band", formatBand(item.band)),
                        fact("Finding", item.issue),
                        fact("Suggested improvement", item.suggestion),
                      ]),
                      limitations: [
                        "The explanation is limited to the recorded evaluator feedback for this response.",
                      ],
                    }}
                    prompt={`Why did my Writing Task ${taskNumber} ${item.label} receive band ${formatBand(item.band)}? Explain the recorded finding and turn it into one concrete revision.`}
                    className="h-7 w-7"
                  />
                </div>
              </div>
              <p className="text-xs leading-relaxed text-fg-muted">
                {item.issue}
              </p>
            </div>
          );
        })}
      </div>

      {expanded && (
        <div
          data-testid={`task-${taskNumber}-expanded`}
          className="border-t border-border px-5 py-4"
        >
          <div className="mb-4 space-y-3">
            {topIssues.map((item) => {
              const colours = CRITERION_COLOURS[item.criterion];

              return (
                <div key={item.criterion} className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-fg-muted">
                      {item.label}
                    </span>
                    <span
                      className="font-bold"
                      style={{ color: colours?.text ?? "var(--color-fg-muted)" }}
                    >
                      Band {formatBand(item.band)}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-canvas-inset">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${(item.band / 9) * 100}%`,
                        background: colours?.text ?? "var(--color-fg-muted)",
                      }}
                    />
                  </div>
                  {item.suggestion && (
                    <p className="text-xs leading-relaxed text-fg-subtle">
                      <span className="font-medium text-fg-muted">
                        Suggestion:{" "}
                      </span>
                      {item.suggestion}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/*
            EssayHighlighter is GOA-043's component, reused unchanged. Its issue
            shape differs from the writing service's, so toEssayIssues adapts at
            this boundary rather than either side being rewritten.
          */}
          <div className="max-h-72 overflow-y-auto rounded-xl border border-border bg-canvas-subtle p-3">
            <EssayHighlighter essayText={essayText} issues={essayIssues} />
          </div>
        </div>
      )}
    </div>
  );
}

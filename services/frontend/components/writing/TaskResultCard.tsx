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
}: TaskResultCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const topIssues = topIssuePerCriterion(evaluations);
  const essayIssues = toEssayIssues(evaluations);

  return (
    <div
      data-testid={`task-${taskNumber}-result-card`}
      data-expanded={expanded}
      className="rounded-2xl border border-gray-200/80 bg-white shadow-2xs"
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        data-testid={`task-${taskNumber}-result-toggle`}
        className="flex w-full items-center justify-between gap-4 p-5 text-left"
      >
        <div className="flex items-center gap-3">
          {expanded ? (
            <ChevronDown size={16} className="text-gray-400" />
          ) : (
            <ChevronRight size={16} className="text-gray-400" />
          )}
          <div>
            <h4 className="font-serif text-sm font-bold text-gray-900">
              Task {taskNumber} — evaluated
            </h4>
            <p className="text-xs text-gray-500">
              {wordCount} words · {expanded ? "Hide" : "Show"} full feedback
            </p>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">
            Band
          </p>
          <p
            data-testid={`task-${taskNumber}-band`}
            className="font-serif text-2xl font-bold text-[#0d4d3a]"
          >
            {formatBand(overallBand)}
          </p>
        </div>
      </button>

      {/*
        The penalty is reported by the server (penalty_flag), not recomputed
        here, so the card can never contradict what was actually recorded
        against the submission.
      */}
      {penaltyFlag && (
        <div
          data-testid={`task-${taskNumber}-penalty-warning`}
          className="mx-5 mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
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
              className="rounded-xl border border-gray-100 bg-gray-50/60 p-3"
              style={{ borderLeft: `3px solid ${colours?.text ?? "#6B7280"}` }}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span
                  className="text-[10px] font-bold uppercase tracking-wide"
                  style={{ color: colours?.text ?? "#374151" }}
                >
                  {item.label}
                </span>
                <span className="text-xs font-bold text-gray-700">
                  {formatBand(item.band)}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-gray-600">
                {item.issue}
              </p>
            </div>
          );
        })}
      </div>

      {expanded && (
        <div
          data-testid={`task-${taskNumber}-expanded`}
          className="border-t border-gray-100 px-5 py-4"
        >
          <div className="mb-4 space-y-3">
            {topIssues.map((item) => {
              const colours = CRITERION_COLOURS[item.criterion];

              return (
                <div key={item.criterion} className="space-y-1.5">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-gray-800">
                      {item.label}
                    </span>
                    <span
                      className="font-bold"
                      style={{ color: colours?.text ?? "#374151" }}
                    >
                      Band {formatBand(item.band)}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${(item.band / 9) * 100}%`,
                        background: colours?.text ?? "#6B7280",
                      }}
                    />
                  </div>
                  {item.suggestion && (
                    <p className="text-xs leading-relaxed text-gray-500">
                      <span className="font-medium text-gray-700">
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
          <div className="max-h-72 overflow-y-auto rounded-xl border border-gray-200 bg-[#FAFBF9] p-3">
            <EssayHighlighter essayText={essayText} issues={essayIssues} />
          </div>
        </div>
      )}
    </div>
  );
}

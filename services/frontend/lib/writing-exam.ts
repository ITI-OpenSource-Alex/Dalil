import type { EssayIssue } from "@/components/chat/essay-highlighter";
import type {
  WritingCriterionEvaluation,
  WritingInlineIssue,
} from "@/lib/exam-api";

/**
 * Pure logic for the Writing exam UI (GOA-058).
 *
 * Everything here is deliberately free of React and of `fetch` so it can be
 * unit-tested under vitest with no DOM and no network — the same split
 * lib/reading-grading.ts and lib/reading-results.ts already use for Reading.
 *
 * This module is the single home for the counting/threshold/weighting rules.
 * Duplicating any of them inside a component is how the counter and the
 * server's penalty flag end up disagreeing with each other.
 */

/** Minimum words before IELTS penalises the response, per task. */
export const TASK_WORD_TARGETS: Record<WritingTaskNumber, number> = {
  1: 150,
  2: 250,
};

/**
 * The standard 20/40 split of the 60-minute paper. It mirrors the 33/67 mark
 * weighting — you spend twice as long on the task worth twice as much.
 */
export const TASK_SUGGESTED_MINUTES: Record<WritingTaskNumber, number> = {
  1: 20,
  2: 40,
};

/** Task 1 is worth a third of the Writing band, Task 2 two thirds. */
export const TASK_WEIGHT_PERCENT: Record<WritingTaskNumber, number> = {
  1: 33,
  2: 67,
};

export type WritingTaskNumber = 1 | 2;

/**
 * Verbatim copy required by GOA-058. Frozen into a constant so an incidental
 * edit in a component can't drift the wording of a user-facing claim about how
 * marking works.
 */
export const UNDER_MINIMUM_WARNING =
  "Responses under 150 words are penalised for Task Achievement (criterion 1).";

/**
 * Counts words exactly as GOA-058 specifies.
 *
 * Deliberately naive, and deliberately kept that way: the exam service computes
 * `len(essay_text.split())` (services/exam/app/services/session_service.py) to
 * decide the penalty flag, and Python's bare `split()` splits on the same
 * arbitrary-whitespace runs this does. A "smarter" counter that discarded
 * punctuation-only tokens would look more correct and then disagree with the
 * server about whether a response was under length — which is worse than
 * counting a stray comma.
 */
export function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export type WordCountState = "below" | "met";

/**
 * Below the task's target → "below" (rendered orange), at or above it → "met"
 * (rendered green). One boundary, at the target itself: 149 is below, 150 is
 * met. The ticket's "(140/240)" values are illustrative below-target examples,
 * not a second threshold.
 */
export function wordCountState(
  count: number,
  task: WritingTaskNumber,
): WordCountState {
  return count >= TASK_WORD_TARGETS[task] ? "met" : "below";
}

/** True when the response is short enough to attract the Task Achievement penalty. */
export function isUnderMinimum(count: number, task: WritingTaskNumber): boolean {
  return wordCountState(count, task) === "below";
}

/**
 * Minutes elapsed since the exam started, derived from the countdown rather
 * than a locally-remembered start time so it survives a page reload: the
 * backend re-seeds `remaining_time_seconds` from its own `started_at`.
 */
export function elapsedMinutes(
  timeLimitSeconds: number,
  secondsLeft: number,
): number {
  return Math.max(0, Math.floor((timeLimitSeconds - secondsLeft) / 60));
}

export const CRITERION_LABELS: Record<string, string> = {
  task_response: "Task Response",
  cohesion: "Cohesion & Coherence",
  vocabulary: "Vocabulary",
  grammar: "Grammar",
};

/**
 * Canonical criterion order, matching the writing service's own `CRITERIA`
 * tuple so the UI lists them the same way every time regardless of the order
 * the four parallel agents happened to finish in.
 */
export const CRITERION_ORDER = [
  "task_response",
  "cohesion",
  "vocabulary",
  "grammar",
] as const;

/**
 * Adapts the writing service's inline issues onto the shape EssayHighlighter
 * (GOA-043) expects.
 *
 * The two sides genuinely disagree on names — the service emits
 * `inline_issues: [{ text, issue_type, suggestion, start_char, end_char }]`
 * (services/writing/app/schemas.py) while the highlighter consumes
 * `{ text, issue, suggestion, start, end, criterion }`. Feeding the raw payload
 * straight in renders zero highlights and throws no error, so the mismatch is
 * translated here, at the boundary, rather than by changing either side: the
 * highlighter and lib/writing-api.ts are the chat writing path's contract
 * (GOA-043) and are unit-tested against the current shape.
 */
export function toEssayIssues(
  evaluations: WritingCriterionEvaluation[],
): EssayIssue[] {
  return evaluations.flatMap((evaluation) =>
    (evaluation.inline_issues ?? []).map((issue) => ({
      text: issue.text,
      issue: issue.issue_type,
      suggestion: issue.suggestion,
      start: issue.start_char,
      end: issue.end_char,
      criterion: evaluation.criterion,
    })),
  );
}

export interface TopIssue {
  criterion: string;
  label: string;
  band: number;
  /** The single most relevant thing to fix for this criterion. */
  issue: string;
  suggestion?: string;
}

/**
 * One headline finding per criterion for the collapsed Task 1 card.
 *
 * Prefers the first inline issue, because a quoted phrase from the candidate's
 * own text is more actionable mid-exam than prose. Falls back to the
 * criterion's `feedback` when an agent returned no issues — every criterion
 * always produces feedback, so a criterion never silently disappears from the
 * card just because its agent found nothing to underline.
 */
export function topIssuePerCriterion(
  evaluations: WritingCriterionEvaluation[],
): TopIssue[] {
  const byCriterion = new Map(
    evaluations.map((evaluation) => [evaluation.criterion, evaluation]),
  );

  const ordered = [
    ...CRITERION_ORDER.filter((criterion) => byCriterion.has(criterion)),
    ...evaluations
      .map((evaluation) => evaluation.criterion)
      .filter(
        (criterion) =>
          !(CRITERION_ORDER as readonly string[]).includes(criterion),
      ),
  ];

  return ordered.map((criterion) => {
    const evaluation = byCriterion.get(criterion)!;
    const first: WritingInlineIssue | undefined = evaluation.inline_issues?.[0];

    return {
      criterion,
      label: CRITERION_LABELS[criterion] ?? criterion,
      band: evaluation.band_score,
      issue: first ? first.issue_type : evaluation.feedback,
      suggestion: first?.suggestion,
    };
  });
}

/** One band formatted the way IELTS reports it — always one decimal place. */
export function formatBand(band: number): string {
  return band.toFixed(1);
}

/**
 * Builds the explicit weighting sentence GOA-058 requires, e.g.
 * "(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0".
 *
 * `overallBand` is passed in rather than derived. The exam service already
 * computes `round((t1 + 2*t2) / 3 * 2) / 2` and that value is the one persisted
 * against the session, so recomputing it here would create a second
 * implementation of a marking rule — and the day the two drift, a candidate
 * sees arithmetic that does not add up.
 */
export function formatWeightedFormula(
  task1Band: number,
  task2Band: number,
  overallBand: number,
): string {
  const weighted = (task1Band + 2 * task2Band) / 3;

  return (
    `(Task 1: ${formatBand(task1Band)} × ${TASK_WEIGHT_PERCENT[1]}%) + ` +
    `(Task 2: ${formatBand(task2Band)} × ${TASK_WEIGHT_PERCENT[2]}%) = ` +
    `${weighted.toFixed(1)} → Band ${formatBand(overallBand)}`
  );
}

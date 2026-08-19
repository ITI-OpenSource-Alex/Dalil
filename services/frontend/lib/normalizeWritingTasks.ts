import type { ExamQuestion } from "@/lib/exam-api";

/**
 * A Writing task, normalized into the one shape the UI renders.
 *
 * `stimulusImageUrl` carries the Academic Task 1 chart. The exam service
 * exposes it as a pre-signed URL at the *question-set* level
 * (`ExamQuestion.image_url`, minted at session start), not per task, because a
 * writing question set has exactly one visual stimulus and it is always Task
 * 1's — so it is threaded onto task 1 here and left undefined everywhere else
 * (General Training Task 1, Task 2, and any set whose `image_url` is null,
 * which is every non-Academic-Task-1 payload).
 */
export interface NormalizedWritingTask {
  taskNumber: 1 | 2;
  prompt: string;
  /** Sub-instruction, e.g. "Write at least 150 words." Absent in some books. */
  instructions?: string;
  /**
   * Pre-signed, browser-reachable URL for the Academic Task 1 stimulus chart.
   * Only ever set on task 1, and only when the session payload carried one.
   */
  stimulusImageUrl?: string;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0
    ? value
    : undefined;
}

/**
 * Turns the session payload's `questions` array into exactly two Writing tasks.
 *
 * Two different JSON shapes reach this function, and both are real:
 *
 *   A) a LIST, one entry per task — what every ingested Cambridge book produces
 *      (services/exam/app/ingestion/writing_parser.py):
 *        [{ number: 1, prompt, question_type, instructions }, { number: 2, ... }]
 *
 *   B) a DICT keyed by task — used by seeded and fixture data:
 *        { task1: { prompt }, task2: { prompt } }
 *      The exam service's `_question_list` wraps a bare dict into a
 *      single-element list on the way out, so this arrives as
 *      `[{ task1: {...}, task2: {...} }]`.
 *
 * Handling both here — rather than assuming one — is what keeps the exam
 * renderable regardless of which ingestion produced the question row. The
 * previous inline implementation in the exam shell indexed
 * `questions[0].questions[0].prompt` positionally, which silently mis-renders
 * shape B and throws on any book that yielded fewer than two parsed tasks.
 *
 * (The exam service's own `_resolve_task_context` had the mirror-image bug —
 * it assumed shape B and raised AttributeError on shape A, returning HTTP 500
 * on every real writing submit. Both sides now handle both shapes.)
 *
 * The Academic Task 1 stimulus URL is read from the question set itself
 * (`image_url`), not from a per-task entry — the exam service pre-signs it at
 * `QuestionResponse` level because a writing set has a single visual stimulus,
 * always Task 1's. It is attached to task 1 only and is undefined whenever the
 * payload carried no image (null `image_url`), which covers General Training
 * and Task 2.
 */
export function normalizeWritingTasks(
  questionSets: ExamQuestion[] | undefined,
): NormalizedWritingTask[] {
  const set = questionSets?.[0];
  const entries = set?.questions ?? [];
  const stimulusImageUrl = asString(set?.image_url ?? undefined);
  const first = entries[0] as Record<string, unknown> | undefined;

  // Shape B: a single wrapper object carrying task1/task2 keys.
  if (first && (first.task1 !== undefined || first.task2 !== undefined)) {
    return ([1, 2] as const)
      .map((taskNumber): NormalizedWritingTask | null => {
        const task = first[`task${taskNumber}`] as
          | Record<string, unknown>
          | undefined;
        const prompt = asString(task?.prompt);
        if (!task || !prompt) return null;

        return {
          taskNumber,
          prompt,
          instructions: asString(task.instructions),
          ...(taskNumber === 1 && stimulusImageUrl ? { stimulusImageUrl } : {}),
        };
      })
      .filter((task): task is NormalizedWritingTask => task !== null);
  }

  // Shape A: one entry per task. `number` is authoritative when present so the
  // tasks can't be swapped by array order; index is only a fallback.
  return entries
    .map((entry, index): NormalizedWritingTask | null => {
      const source = entry as Record<string, unknown>;
      const prompt = asString(source.prompt);
      if (!prompt) return null;

      const declared = source.number;
      const taskNumber: 1 | 2 = declared === 2 || index === 1 ? 2 : 1;

      return {
        taskNumber,
        prompt,
        instructions: asString(source.instructions),
        ...(taskNumber === 1 && stimulusImageUrl ? { stimulusImageUrl } : {}),
      };
    })
    .filter((task): task is NormalizedWritingTask => task !== null)
    .slice(0, 2);
}

/** Looks up one task, or undefined when the book yielded fewer than two. */
export function findWritingTask(
  tasks: NormalizedWritingTask[],
  taskNumber: 1 | 2,
): NormalizedWritingTask | undefined {
  return tasks.find((task) => task.taskNumber === taskNumber);
}

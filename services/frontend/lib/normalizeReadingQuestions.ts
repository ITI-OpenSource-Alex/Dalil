import type {
  NormalizedReadingQuestion,
  RawReadingQuestion,
  ReadingUiType,
} from "@/app/types/reading";
import { sectionForQuestionNumber } from "@/lib/reading-sections";

// The backend's question_type values (confirmed against real ingested data
// and services/exam/app/ingestion/parser.py's SUPPORTED_QUESTION_TYPES) are
// far more granular than the 5 UI categories GOA-055 renders. This is the
// single place that bucketing happens — QuestionRenderer and
// QuestionTypeBreakdown both consume `uiType` from here rather than each
// re-deriving their own mapping, so the renderer and the results-page
// breakdown can never disagree about what a question "is".
function toUiType(rawQuestionType: string | null | undefined): ReadingUiType {
  // question_type comes straight off the session API response (an external
  // boundary, not a value this code controls) — a missing/non-string value
  // shouldn't crash the whole exam, it's just as "unclassified" as any other
  // type this function doesn't recognize.
  if (typeof rawQuestionType !== "string") return "short_answer";

  const t = rawQuestionType.toLowerCase();

  if (t.includes("matching") || t.includes("map labelling")) return "matching";
  if (
    t.includes("true") ||
    t.includes("false") ||
    (t.includes("yes") && t.includes("no")) ||
    t.includes("not given")
  ) {
    return "true_false_not_given";
  }
  if (
    t.includes("completion") ||
    t.includes("fill in") ||
    t.includes("fill-in") ||
    t.includes("blank")
  ) {
    return "fill_in_blank";
  }
  if (t.includes("multiple choice")) return "multiple_choice";
  if (t.includes("short answer")) return "short_answer";

  // Unknown/unclassified backend type: short answer (a plain text input) is
  // the safest universal fallback — it always lets the user answer
  // something and never crashes the exam, unlike assuming a fixed option
  // set that may not exist for this question.
  return "short_answer";
}

// Interim workaround for the "no structured options field" gap (see the
// GOA-055 blocker/risk analysis): Multiple Choice and Matching option text
// is embedded in the free-text `prompt` rather than a discrete backend
// field. This parses the common Cambridge convention of one option per
// line, marked "A.", "A)", or "A " at the start of the line. It is
// deliberately conservative — returns undefined rather than a wrong guess
// when fewer than 2 confident option lines are found, so callers must
// treat `options` as optional and fall back to a plain text input.
const OPTION_LINE = /^\s*([A-H])[.)]\s+(.+)$/;

function parseInlineOptions(
  prompt: string,
): { options: string[]; stem: string } | undefined {
  const lines = prompt.split(/\r?\n/);
  const options: string[] = [];
  const stemLines: string[] = [];

  for (const line of lines) {
    const match = OPTION_LINE.exec(line);
    if (match) {
      options.push(match[2].trim());
    } else if (line.trim()) {
      stemLines.push(line.trim());
    }
  }

  if (options.length < 2) return undefined;

  return { options, stem: stemLines.join(" ").trim() };
}

export function normalizeReadingQuestions(
  raw: RawReadingQuestion[],
): NormalizedReadingQuestion[] {
  return raw.map((q) => {
    const uiType = toUiType(q.question_type);
    const needsOptions = uiType === "multiple_choice" || uiType === "matching";
    const parsed = needsOptions ? parseInlineOptions(q.prompt) : undefined;
    const structuredOptions =
      needsOptions && Array.isArray(q.options) && q.options.length >= 2
        ? q.options.map((option) => option.trim()).filter(Boolean)
        : undefined;

    return {
      number: q.number,
      prompt: q.prompt,
      promptStem: structuredOptions ? q.prompt : parsed?.stem || q.prompt,
      rawQuestionType: q.question_type,
      uiType,
      instructions: q.instructions,
      passageNumber: q.passage_number,
      section: sectionForQuestionNumber(q.number),
      options: structuredOptions ?? parsed?.options,
    };
  });
}

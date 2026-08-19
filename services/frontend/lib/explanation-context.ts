export type ExplanationKind =
  | "speaking_score"
  | "writing_score"
  | "exam_score"
  | "programme_match"
  | "cv_review"
  | "recommendation"
  | "checklist"
  | "visa_requirement";

export interface ExplanationFact {
  label: string;
  value: string;
  sourceUrl?: string;
}

/**
 * Evidence for one conversational explanation turn.
 *
 * The card is visible and removable in the composer. It is deliberately not
 * stored as a permanent chat mode: after this question, Dalil is the same
 * general-purpose assistant it was before the user clicked the icon.
 */
export interface ExplanationContext {
  kind: ExplanationKind;
  title: string;
  subjectId?: string;
  summary?: string;
  facts: ExplanationFact[];
  limitations?: string[];
}

export function defaultExplanationPrompt(context: ExplanationContext): string {
  return `Explain ${context.title.toLowerCase()}. Show me which evidence affected it, what it does not prove, and what I can do next.`;
}

export function fact(
  label: string,
  value: string | number | null | undefined,
  sourceUrl?: string | null,
): ExplanationFact | null {
  if (value === null || value === undefined || value === "") return null;
  return {
    label: label.slice(0, 80),
    value: String(value).slice(0, 500),
    ...(sourceUrl ? { sourceUrl: sourceUrl.slice(0, 500) } : {}),
  };
}

export function compactFacts(
  facts: Array<ExplanationFact | null | undefined | false>,
): ExplanationFact[] {
  return facts.filter((item): item is ExplanationFact => Boolean(item));
}

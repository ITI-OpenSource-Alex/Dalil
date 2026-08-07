import {
  SpeakingCriteriaScores,
  SpeakingDimensions,
} from "@/app/types/speaking";

// The evaluation swarm (services/speaking/agents/swarm.go) keys its output
// by these long-form dimension names — not the short "fluency" style keys
// used elsewhere in the UI. This is the single place that maps between them
// so every consumer (live chat panel, history detail, public share page)
// reads the same, correct values.
const DIMENSION_KEY_MAP: Record<keyof SpeakingCriteriaScores, string> = {
  fluency: "Fluency and Coherence",
  lexical: "Lexical Resource",
  grammar: "Grammatical Range and Accuracy",
  pronunciation: "Pronunciation",
};

export function extractCriteriaScores(
  dimensions: SpeakingDimensions | null | undefined,
): SpeakingCriteriaScores {
  // null, not 0. A missing or timed-out criterion has no band, and 0 is a
  // valid IELTS score — defaulting to it reported an evaluation that never
  // happened as a very bad one (GOA-032, BUG-055).
  const scores: SpeakingCriteriaScores = {
    fluency: null,
    lexical: null,
    grammar: null,
    pronunciation: null,
  };

  if (!dimensions) return scores;

  (Object.keys(DIMENSION_KEY_MAP) as (keyof SpeakingCriteriaScores)[]).forEach(
    (key) => {
      const dimension = dimensions[DIMENSION_KEY_MAP[key]];
      scores[key] =
        dimension && !dimension.timed_out ? (dimension.band ?? null) : null;
    },
  );

  return scores;
}

export function formatSessionDate(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;

  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatSessionDateTime(isoDate: string): string {
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) return isoDate;

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

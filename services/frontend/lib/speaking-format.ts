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
  const scores: SpeakingCriteriaScores = {
    fluency: 0,
    lexical: 0,
    grammar: 0,
    pronunciation: 0,
  };

  if (!dimensions) return scores;

  (Object.keys(DIMENSION_KEY_MAP) as (keyof SpeakingCriteriaScores)[]).forEach(
    (key) => {
      scores[key] = dimensions[DIMENSION_KEY_MAP[key]]?.band ?? 0;
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

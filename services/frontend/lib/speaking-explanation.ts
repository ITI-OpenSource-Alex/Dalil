/**
 * The explanation a speaking session was scored with (SPEAK-EVAL-008).
 *
 * These types mirror `services/speaking/internal/contract/explanation.go`. The
 * server decides what may be displayed; this file only describes the shape of
 * that decision and provides the copy for it.
 *
 * The rule that runs through all of it: **this module never repairs anything.**
 * If a claim is not in `claims`, it was withheld by the validator and must not
 * be reconstructed here from the raw evaluation. Doing so would put back exactly
 * what the validator removed, one layer further from the check.
 */

/** Statement kinds, in the order a criterion presents them. */
export type ClaimKind = "rubric" | "evidence" | "summary" | "action";

export type Polarity = "supports" | "caps_below" | "reaches_toward";

export type WithholdReason =
  | "descriptor_not_in_rubric"
  | "descriptor_belongs_to_another_criterion"
  | "quote_not_found_at_offsets"
  | "measurement_not_in_provenance"
  | "evidence_incomplete"
  | "no_resolved_support";

export interface Claim {
  Kind: ClaimKind;
  Text: string;

  DescriptorID?: string;
  DescriptorBand?: number;
  Polarity?: Polarity;

  Quote?: string;
  CharStart?: number;
  CharEnd?: number;

  AudioStartS?: number;
  AudioEndS?: number;

  MeasurementID?: string;
  MeasurementValue?: number;
  MeasurementUnit?: string;

  /** Populated once a session is a multi-turn interview. Absent today. */
  TurnID?: string;
  Part?: number;
}

export interface WithheldClaim {
  Kind: ClaimKind;
  Reason: WithholdReason;
  Detail: string;
}

export interface RenderableCriterion {
  CriterionID: string;
  Status: "scored" | "unavailable";
  /** Absent — not zero — when the criterion produced no score. */
  Band?: number;
  UnavailableReason?: string;
  Claims?: Claim[];
  Withheld?: WithheldClaim[];
  Limitations?: string[];
}

export interface Renderable {
  EvaluationID: string;
  Mode: string;
  Status: "complete" | "partial" | "failed";
  Band?: number;
  UnroundedMean?: number;
  /** Present when no overall band was calculated; already written for display. */
  BandWithheldReason?: string;
  Criteria?: RenderableCriterion[];
  ScoreSemantics: string;
  RubricID: string;
  RubricVersion: string;
}

export interface ExplanationMeta {
  rubric_id: string;
  rubric_version: string;
  scorer_version: string;
  llm_model?: string;
  claim_count: number;
  withheld_count: number;
}

const CRITERION_LABELS: Record<string, string> = {
  fluency_coherence: "Fluency and Coherence",
  lexical_resource: "Lexical Resource",
  grammatical_range: "Grammatical Range and Accuracy",
  pronunciation: "Pronunciation",
};

export function criterionLabel(id: string): string {
  return CRITERION_LABELS[id] ?? id;
}

/**
 * Why a criterion could not be scored, in words a student can act on.
 *
 * Each reason gets its own sentence because they call for different responses:
 * a deadline is worth retrying, a provider error is not the student's problem
 * at all, and insufficient evidence means the recording itself was the limit.
 * Collapsing them into "unavailable" would leave a student unable to tell
 * whether to try again.
 */
export function unavailableCopy(reason?: string): string {
  switch (reason) {
    case "deadline_exceeded":
      return "This criterion took too long to assess and was not completed. Trying again usually works.";
    case "provider_error":
      return "This criterion could not be assessed because of a problem on our side. Nothing about your answer caused it.";
    case "invalid_output":
      return "This criterion could not be assessed because the response could not be read. Trying again usually works.";
    case "insufficient_evidence":
      return "There was not enough in this recording to assess this criterion.";
    default:
      return "This criterion was not assessed.";
  }
}

/**
 * What a cited descriptor establishes.
 *
 * `caps_below` is the one that matters: it is the difference between an
 * explanation a student can act on and one they can only accept. "Why not a 7"
 * is more useful than "why a 6".
 */
export function polarityCopy(polarity?: Polarity): string {
  switch (polarity) {
    case "supports":
      return "What you did";
    case "caps_below":
      return "What would take you higher";
    case "reaches_toward":
      return "Emerging";
    default:
      return "Related";
  }
}

/**
 * The sentence shown when claims were suppressed.
 *
 * Displayed, not swallowed. The acceptance criterion is that invalid
 * explanations are never *silently* shown, and a student comparing two sessions
 * should be able to tell a quiet one from a broken one.
 */
export function withheldNotice(count: number): string | null {
  if (count <= 0) return null;
  if (count === 1) {
    return "1 further observation could not be verified against your answer, so it is not shown.";
  }
  return `${count} further observations could not be verified against your answer, so they are not shown.`;
}

/**
 * The qualifier that must travel with every band.
 *
 * `score_semantics` is `estimated_ielts_practice_band` and this is what that
 * means in words. A band shown without it implies a certified assessment, which
 * this system must never claim.
 */
export function scoreSemanticsCopy(semantics: string): string {
  if (semantics === "estimated_ielts_practice_band") {
    return "Estimated practice band. Not an official IELTS score.";
  }
  return "Practice estimate.";
}

export function totalWithheld(renderable: Renderable): number {
  return (renderable.Criteria ?? []).reduce(
    (sum, criterion) => sum + (criterion.Withheld?.length ?? 0),
    0,
  );
}

export function isScored(
  criterion: RenderableCriterion,
): criterion is RenderableCriterion & { Band: number } {
  return criterion.Status === "scored" && typeof criterion.Band === "number";
}

/** Claims of one kind, in server order. Order is meaning: it is the order the validator resolved them in. */
export function claimsOfKind(
  criterion: RenderableCriterion,
  kind: ClaimKind,
): Claim[] {
  return (criterion.Claims ?? []).filter((claim) => claim.Kind === kind);
}

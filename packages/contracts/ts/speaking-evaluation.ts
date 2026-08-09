/**
 * TypeScript representation of the canonical speaking evaluation
 * (SPEAK-EVAL-003).
 *
 * Source of truth: packages/contracts/schemas/speaking-evaluation-v1.schema.json
 * Go:              services/speaking/internal/contract
 * Python:          packages/contracts/py/contracts/speaking_evaluation.py
 *
 * All three decode the same fixtures in
 * packages/contracts/fixtures/speaking-evaluation, because the drift this
 * contract replaces was three representations that each looked correct alone.
 *
 * Two rules run through every type here:
 *
 * 1. Status is separate from value. A criterion that did not complete has
 *    status "unavailable" and NO band field. Band 0.0 is a real IELTS value
 *    meaning the candidate said nothing usable; it must never stand in for "we
 *    did not measure this". The discriminated union below makes reading a band
 *    off an unavailable criterion a compile error rather than a runtime surprise.
 *
 * 2. Every claim is addressable. A rubric match names a descriptor id from the
 *    frozen rubric; evidence names a transcript offset, an audio interval or a
 *    measurement id.
 */

export const SPEAKING_EVALUATION_SCHEMA_VERSION = "speaking-evaluation/v1";
export const SCORE_SEMANTICS = "estimated_ielts_practice_band";
export const ROUNDING_RULE_V1 = "ielts_half_band_v1";

/**
 * The four official IELTS speaking criteria.
 *
 * Snake_case ids rather than display strings: a label is a presentation
 * concern and changes. GOA-133 renamed pronunciation in the UI without
 * touching the underlying criterion, which is exactly the separation this buys.
 */
export type CriterionId =
  | "fluency_coherence"
  | "lexical_resource"
  | "grammatical_range"
  | "pronunciation";

export type Mode = "practice" | "exam" | "benchmark";

export type EvaluationStatus = "complete" | "partial" | "failed";

export type UnavailableReason =
  | "provider_error"
  | "deadline_exceeded"
  | "invalid_output"
  | "insufficient_evidence";

/** `caps_below` is what lets an explanation answer "why not a 7". */
export type Polarity = "supports" | "caps_below" | "reaches_toward";

export type EvidenceKind =
  | "transcript_span"
  | "audio_interval"
  | "measurement_ref"
  | "part_or_turn"
  | "absence_or_distribution";

export type MeasurementUnit =
  | "words_per_minute"
  | "seconds"
  | "count"
  | "ratio"
  | "probability";

export interface RubricMatch {
  rubric_id: string;
  rubric_version: string;
  /** Must exist in the frozen rubric; anything else is an invented citation. */
  descriptor_id: string;
  descriptor_band: number;
  polarity: Polarity;
  application?: string;
}

export interface Evidence {
  kind: EvidenceKind;
  /** What this is evidence FOR. Evidence attached to nothing is decoration. */
  supports_claim: string;

  quote?: string;
  char_start?: number;
  char_end?: number;

  audio_start_s?: number;
  audio_end_s?: number;

  measurement_id?: string;
  part?: number;
}

export interface ImprovementAction {
  action: string;
  because?: string;
}

interface CriterionResultBase {
  criterion_id: CriterionId;
  summary?: string;
  rubric_matches?: RubricMatch[];
  evidence?: Evidence[];
  measurements?: string[];
  limitations?: string[];
  improvement_actions?: ImprovementAction[];
}

/**
 * A criterion that produced a score.
 *
 * `band` is required here and absent from the unavailable variant, so
 * `result.band` does not type-check until the caller has narrowed on `status`.
 * That is the point: the previous shape let a UI read a band off a criterion
 * that never produced one and render 0.
 */
export interface ScoredCriterion extends CriterionResultBase {
  status: "scored";
  band: number;
}

export interface UnavailableCriterion extends CriterionResultBase {
  status: "unavailable";
  unavailable_reason: UnavailableReason;
}

export type CriterionResult = ScoredCriterion | UnavailableCriterion;

/** Narrowing helper, so consumers do not hand-roll the status check. */
export function isScored(c: CriterionResult): c is ScoredCriterion {
  return c.status === "scored";
}

export interface Overall {
  /**
   * ABSENT -- not null, not zero -- when fewer than `min_criteria_required`
   * criteria scored. A band averaged from one surviving agent describes which
   * agents survived, not the candidate (BUG-040).
   */
  band?: number;
  /** The mean before rounding, so the arithmetic is visible rather than trusted. */
  unrounded_mean?: number;
  included_criteria: CriterionId[];
  excluded_criteria?: CriterionId[];
  rounding_rule: string;
  min_criteria_required: number;
}

export interface Measurement {
  id: string;
  name: string;
  value: number;
  unit: MeasurementUnit;
  extractor_version: string;
  scope?: "utterance" | "part" | "session";
}

export interface Provenance {
  created_at: string;
  scorer_version: string;
  rubric_id: string;
  rubric_version: string;
  rubric_sha256?: string;

  llm_provider?: string;
  /**
   * The EFFECTIVE model, read from configuration at call time. This was
   * hardcoded to a Haiku id in the Langfuse span while the service ran Opus,
   * which made every model-to-model telemetry comparison meaningless.
   */
  llm_model?: string;
  prompt_template_ids?: string[];

  stt_provider?: string;
  stt_model?: string;
  transcript_sha256?: string;
  /** SPEAK-EVAL-002: a mislabelled format silently produces a score from noise. */
  audio_format?: string;
  feature_extractor_version?: string;

  measurements?: Measurement[];
}

export interface Telemetry {
  total_latency_ms?: number;
  transcription_ms?: number;
  audio_duration_s?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  /**
   * `null`, never 0, when the model is absent from the shared price table
   * (GOA-135). "We could not price this" and "this was free" are different facts.
   */
  cost_usd?: number | null;
}

export interface SpeakingEvaluation {
  schema_version: typeof SPEAKING_EVALUATION_SCHEMA_VERSION;
  evaluation_id: string;
  mode: Mode;
  status: EvaluationStatus;
  score_semantics: typeof SCORE_SEMANTICS;
  criteria: CriterionResult[];
  overall: Overall;
  provenance: Provenance;
  telemetry?: Telemetry;
}

/** A legal IELTS band: 0..9 in half steps. */
export function isHalfBand(value: number): boolean {
  if (value < 0 || value > 9) return false;
  return Math.abs(value * 2 - Math.round(value * 2)) < 1e-9;
}

/** Official half-up rounding. Mirrors the Go and Python implementations. */
export function roundIeltsBand(average: number): number {
  const intPart = Math.trunc(average);
  const dec = average - intPart;
  if (dec < 0.25) return intPart;
  if (dec < 0.75) return intPart + 0.5;
  return intPart + 1.0;
}

/**
 * Runtime validation for a payload arriving over the wire.
 *
 * TypeScript types vanish at runtime, so a WebSocket frame is `any` until
 * something checks it. This returns the problems rather than throwing, so a UI
 * can decline to render an invalid result while still showing the rest of the
 * session.
 */
interface RawCriterion {
  criterion_id?: CriterionId;
  status?: string;
  band?: number;
  unavailable_reason?: string;
  measurements?: string[];
  evidence?: Evidence[];
}

export function validateSpeakingEvaluation(input: unknown): string[] {
  const problems: string[] = [];
  const e = input as Partial<SpeakingEvaluation>;

  if (!e || typeof e !== "object") return ["payload is not an object"];

  if (e.schema_version !== SPEAKING_EVALUATION_SCHEMA_VERSION) {
    problems.push(
      `schema_version is ${JSON.stringify(e.schema_version)}, expected ${SPEAKING_EVALUATION_SCHEMA_VERSION}`,
    );
  }
  if (e.score_semantics !== SCORE_SEMANTICS) {
    problems.push(
      `score_semantics is ${JSON.stringify(e.score_semantics)}; this system must not claim to be a certified examiner`,
    );
  }
  if (!Array.isArray(e.criteria) || e.criteria.length === 0) {
    problems.push("criteria is missing or empty");
    return problems;
  }

  // Provenance is required, not decorative. A result with no record of which
  // rubric, prompt and model produced it cannot be explained after the fact,
  // and an unexplainable score is the thing this contract exists to prevent.
  if (!e.provenance || typeof e.provenance !== "object") {
    problems.push("provenance is missing");
  } else {
    for (const field of ["created_at", "scorer_version", "rubric_id", "rubric_version"] as const) {
      if (!e.provenance[field]) {
        problems.push(`provenance.${field} is missing`);
      }
    }
  }

  const measurementIds = new Set(
    (e.provenance?.measurements ?? []).map((m) => m.id),
  );

  let scoredCount = 0;
  // Deliberately looser than CriterionResult. The compile-time union is
  // exhaustive, so narrowing on it would make the unknown-status branch below
  // `never` -- but this function exists precisely because the payload has not
  // been validated yet, and at runtime an unknown status is exactly what a
  // version skew produces.
  for (const c of e.criteria as unknown as RawCriterion[]) {
    const where = `criteria[${c.criterion_id}]`;
    if (c.status === "scored") {
      const band = c.band;
      if (typeof band !== "number") {
        problems.push(`${where}: status is scored but band is missing`);
      } else {
        scoredCount++;
        if (!isHalfBand(band)) {
          problems.push(`${where}: band ${band} is not a half-band step`);
        }
      }
    } else if (c.status === "unavailable") {
      if (c.band !== undefined) {
        problems.push(
          `${where}: an unavailable criterion carries a band. Band 0.0 is a real IELTS value and must never mean "not measured" (BUG-055)`,
        );
      }
      if (!c.unavailable_reason) {
        problems.push(`${where}: unavailable with no reason`);
      }
    } else {
      problems.push(`${where}: unknown status ${JSON.stringify(c.status)}`);
    }

    for (const id of c.measurements ?? []) {
      if (!measurementIds.has(id)) {
        problems.push(`${where}: measurement ${id} is not in provenance.measurements`);
      }
    }
    for (const ev of c.evidence ?? []) {
      if (ev.kind === "transcript_span" && (ev.char_start === undefined || ev.char_end === undefined || !ev.quote)) {
        problems.push(`${where}: a transcript span needs a quote and both offsets`);
      }
      if (ev.kind === "measurement_ref" && ev.measurement_id && !measurementIds.has(ev.measurement_id)) {
        problems.push(`${where}: evidence measurement ${ev.measurement_id} does not resolve`);
      }
    }
  }

  const overall = e.overall;
  if (!overall) {
    problems.push("overall is missing");
    return problems;
  }
  if (typeof overall.min_criteria_required !== "number") {
    problems.push("overall.min_criteria_required is missing; the threshold cannot be implicit");
    return problems;
  }
  if (!overall.rounding_rule) {
    problems.push("overall.rounding_rule is missing; a band with no stated rounding rule cannot be reproduced");
  }

  const enough = scoredCount >= overall.min_criteria_required;
  if (overall.band === undefined && enough) {
    problems.push(
      `${scoredCount} criteria scored (threshold ${overall.min_criteria_required}) but no overall band was computed`,
    );
  }
  if (overall.band !== undefined && !enough) {
    problems.push(
      `an overall band of ${overall.band} was computed from ${scoredCount} criteria, below the threshold of ${overall.min_criteria_required} (BUG-040)`,
    );
  }

  return problems;
}

/**
 * Emit the TypeScript implementation's view of a speaking evaluation fixture.
 *
 * Companion to services/speaking/cmd/contract-digest and emit_python.py. The
 * digest format is defined in README.md next to this file; the three emitters
 * must produce identical lines for the same fixture.
 *
 * TypeScript's position here is different from the other two by design. Go and
 * Python reject a bad payload at decode; TypeScript has no runtime types at all,
 * so the same defects surface through validateSpeakingEvaluation. The digest
 * hides that difference on purpose -- see the README on why the verdict is
 * compared and the stage is not.
 */

// Minimal ambient declarations rather than a dependency on @types/node. This
// file is run by the conformance driver through plain node; pulling in a types
// package for two globals would add an install step to a harness whose whole
// value is that it runs anywhere the three toolchains do.
declare const require: (m: string) => any;
declare const process: {
  argv: string[];
  stdout: { write(s: string): void };
  stderr: { write(s: string): void };
  exit(code: number): void;
};

import {
  isScored,
  roundIeltsBand,
  validateSpeakingEvaluation,
  type CriterionResult,
  type SpeakingEvaluation,
} from "../ts/speaking-evaluation.js";

/**
 * "absent" and "0.0000" are different strings, and keeping them different is
 * the point of the harness.
 */
function optFloat(value: number | null | undefined): string {
  if (value === null || value === undefined) return "absent";
  return value.toFixed(4);
}

function optString(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "absent";
  return value;
}

function join(items: string[]): string {
  return items.length > 0 ? items.join(",") : "-";
}

function criterionLines(index: number, c: CriterionResult): string[] {
  const p = `criterion[${index}]`;
  return [
    `${p}.criterion_id=${c.criterion_id}`,
    `${p}.status=${c.status}`,
    `${p}.band=${optFloat(isScored(c) ? c.band : undefined)}`,
    `${p}.unavailable_reason=${optString(isScored(c) ? undefined : c.unavailable_reason)}`,
    `${p}.rubric_match_ids=${join((c.rubric_matches ?? []).map((m) => m.descriptor_id))}`,
    `${p}.evidence_kinds=${join((c.evidence ?? []).map((e) => e.kind))}`,
    `${p}.measurements=${join([...(c.measurements ?? [])])}`,
    `${p}.limitations_count=${(c.limitations ?? []).length}`,
    `${p}.improvement_actions_count=${(c.improvement_actions ?? []).length}`,
  ];
}

function digest(raw: string): string[] | null {
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch (err) {
    process.stderr.write(`typescript: not valid JSON: ${String(err)}\n`);
    return null;
  }

  const problems = validateSpeakingEvaluation(payload);
  if (problems.length > 0) {
    for (const p of problems) process.stderr.write(`typescript: ${p}\n`);
    return null;
  }

  // Only now is the cast honest: the payload has been checked.
  const e = payload as SpeakingEvaluation;

  const lines: string[] = [
    "verdict=accepted",
    `schema_version=${e.schema_version}`,
    `evaluation_id=${e.evaluation_id}`,
    `mode=${e.mode}`,
    `status=${e.status}`,
    `score_semantics=${e.score_semantics}`,
    `criteria_count=${e.criteria.length}`,
  ];

  const scored: number[] = [];
  e.criteria.forEach((c, i) => {
    lines.push(...criterionLines(i, c));
    if (isScored(c)) scored.push(c.band);
  });

  lines.push(
    `scored_count=${scored.length}`,
    `min_criteria_required=${e.overall.min_criteria_required}`,
    `overall.band=${optFloat(e.overall.band)}`,
    `overall.unrounded_mean=${optFloat(e.overall.unrounded_mean)}`,
    `overall.included=${join([...e.overall.included_criteria])}`,
    `overall.excluded=${join([...(e.overall.excluded_criteria ?? [])])}`,
    `overall.rounding_rule=${e.overall.rounding_rule}`,
  );

  // Recomputed, not echoed: this is the line that would catch a rounding rule
  // that drifted in one language only.
  const thresholdMet = scored.length >= e.overall.min_criteria_required;
  lines.push(`derived.threshold_met=${thresholdMet}`);
  if (thresholdMet && scored.length > 0) {
    const mean = scored.reduce((a, b) => a + b, 0) / scored.length;
    lines.push(`derived.mean_of_scored=${mean.toFixed(4)}`);
    lines.push(`derived.rounded_band=${roundIeltsBand(mean).toFixed(4)}`);
  } else {
    lines.push("derived.mean_of_scored=absent");
    lines.push("derived.rounded_band=absent");
  }

  const measurementIds = (e.provenance.measurements ?? [])
    .map((m) => m.id)
    .sort();

  lines.push(
    `provenance.rubric_id=${e.provenance.rubric_id}`,
    `provenance.rubric_version=${e.provenance.rubric_version}`,
    `provenance.scorer_version=${e.provenance.scorer_version}`,
    `provenance.llm_model=${optString(e.provenance.llm_model)}`,
    `provenance.audio_format=${optString(e.provenance.audio_format)}`,
    `provenance.measurement_ids=${join(measurementIds)}`,
  );

  if (e.telemetry === undefined) {
    lines.push("telemetry.present=false", "telemetry.cost_usd=absent");
  } else {
    lines.push("telemetry.present=true", `telemetry.cost_usd=${optFloat(e.telemetry.cost_usd)}`);
  }

  lines.push("validation_problems=0");
  return lines;
}

function main(): void {
  const fs = require("fs");
  const path = process.argv[2];
  if (typeof path !== "string") {
    process.stderr.write("usage: emit_typescript <fixture.json>\n");
    process.exit(2);
    return;
  }

  let raw: string;
  try {
    raw = fs.readFileSync(path, "utf8");
  } catch (err) {
    process.stderr.write(`emit_typescript: ${String(err)}\n`);
    process.exit(2);
    return;
  }

  const lines = digest(raw);
  process.stdout.write(lines !== null ? lines.join("\n") + "\n" : "verdict=rejected\n");
}

main();

/**
 * GOA-030 — step-level timing as a real, queryable metric.
 *
 * The acceptance criterion asks for:
 *
 *   "start and end of each major action logged to CloudWatch custom metric
 *    goa_e2e_step_duration_ms with labels: journey, step"
 *
 * There is no CloudWatch on this project and there is not going to be -- GOA-021
 * never received AWS credentials, which is why both this ticket and GOA-036
 * carry a NO-AWS warning redirecting them to local docker-compose. Prometheus is
 * what this stack actually runs, so the metric keeps its name and both its
 * labels and goes there instead. Anyone reading the AC gets the same series,
 * from a different backend.
 *
 * Pushed rather than scraped because a Playwright run is short-lived, has no
 * stable address, and is over long before the next 15-second scrape would find
 * it. That is the case Pushgateway exists for.
 *
 * Failing to record a metric must never fail a journey. A push that cannot
 * reach the gateway is reported once and then ignored -- the journey's verdict
 * is about the product, not about the observability sidecar.
 */

const PUSHGATEWAY_URL = process.env.PUSHGATEWAY_URL ?? "http://localhost:9091";

export interface StepSample {
  journey: string;
  step: string;
  durationMs: number;
  at: string;
}

/**
 * Attachment name carrying one step's timing from a worker to the reporter.
 *
 * Specs execute in worker PROCESSES; the reporter executes in the main one. A
 * module-level array is therefore two different arrays, and the first version of
 * this file pushed an always-empty one -- a metric pipeline that reported
 * success while emitting nothing, which is the precise failure mode this repo
 * keeps re-finding. Attachments are the supported channel across that boundary.
 */
export const STEP_ATTACHMENT = "goa-step-timing";

const samples: StepSample[] = [];
let warnedOnce = false;

/** Called by the REPORTER as it drains each test's attachments. */
export function recordStep(sample: StepSample): void {
  samples.push(sample);
}

export function collectedSamples(): readonly StepSample[] {
  return samples;
}

/**
 * Escapes a Prometheus label value.
 *
 * Step names are human-written sentences, so quotes and backslashes in one
 * would otherwise produce a body Pushgateway rejects with a 400 that looks
 * nothing like its cause.
 */
function escapeLabel(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, " ");
}

/**
 * Escapes a path segment for the Pushgateway grouping-key URL.
 *
 * A `/` inside a label value would otherwise open a new grouping key and the
 * push would land under a label nobody asked for.
 */
function escapePathSegment(value: string): string {
  return encodeURIComponent(value.replace(/\//g, "_"));
}

/**
 * Pushes everything collected during the run.
 *
 * One push per journey rather than per step: Pushgateway REPLACES all metrics
 * under a grouping key on each PUT, so pushing per step would leave only the
 * last step of each journey visible.
 */
export async function pushCollectedSteps(): Promise<{ pushed: number; ok: boolean }> {
  if (samples.length === 0) return { pushed: 0, ok: true };

  const byJourney = new Map<string, StepSample[]>();
  for (const sample of samples) {
    const bucket = byJourney.get(sample.journey) ?? [];
    bucket.push(sample);
    byJourney.set(sample.journey, bucket);
  }

  let ok = true;
  for (const [journey, journeySamples] of byJourney) {
    const lines = [
      "# HELP goa_e2e_step_duration_ms Duration of one major action in a GOA-030 E2E journey.",
      "# TYPE goa_e2e_step_duration_ms gauge",
    ];
    // A step name can legitimately repeat within a journey (a retry, a poll).
    // Prometheus rejects duplicate label sets in one payload, so identical
    // names collapse to their slowest occurrence -- the one worth alerting on.
    const worst = new Map<string, number>();
    for (const sample of journeySamples) {
      worst.set(sample.step, Math.max(worst.get(sample.step) ?? 0, sample.durationMs));
    }
    for (const [stepName, durationMs] of worst) {
      lines.push(
        `goa_e2e_step_duration_ms{journey="${escapeLabel(journey)}",step="${escapeLabel(stepName)}"} ${durationMs}`,
      );
    }
    const body = `${lines.join("\n")}\n`;

    const url = `${PUSHGATEWAY_URL}/metrics/job/goa_e2e/journey/${escapePathSegment(journey)}`;
    try {
      const response = await fetch(url, { method: "PUT", body });
      if (!response.ok) {
        ok = false;
        if (!warnedOnce) {
          warnedOnce = true;
          console.warn(
            `goa_e2e_step_duration_ms: pushgateway rejected the push (${response.status}): ${await response.text()}`,
          );
        }
      }
    } catch (error) {
      ok = false;
      if (!warnedOnce) {
        warnedOnce = true;
        console.warn(
          `goa_e2e_step_duration_ms: pushgateway unreachable at ${PUSHGATEWAY_URL} (${error}). ` +
            "Step timings are still in the run summary; only the Prometheus series is missing.",
        );
      }
    }
  }

  return { pushed: samples.length, ok };
}

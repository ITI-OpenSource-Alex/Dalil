/**
 * GOA-030 — run summary, artefact collection and S3 upload.
 *
 * Acceptance criteria this implements, verbatim:
 *
 *   "Test run summary uploaded to S3 at tests/e2e/{timestamp}/summary.json
 *    with: pass or fail per journey, screenshots for failures, total duration,
 *    Playwright version"
 *   "Playwright trace files (network requests, DOM snapshots, console logs)
 *    saved on any failure for debugging post-run"
 *
 * "S3" is LocalStack here, for the same NO-AWS reason the metric is Prometheus
 * rather than CloudWatch. The object layout is exactly the one the ticket names,
 * so pointing this at a real account is an endpoint change and nothing else.
 *
 * The upload is best-effort and loudly reported. A reporter that throws takes
 * the whole run's verdict with it, and losing the evidence of a failure is
 * strictly worse than losing the copy of it.
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, copyFileSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import type {
  FullConfig,
  FullResult,
  Reporter,
  TestCase,
  TestResult,
} from "@playwright/test/reporter";
import {
  STEP_ATTACHMENT,
  collectedSamples,
  pushCollectedSteps,
  recordStep,
} from "./metrics";

const BUCKET = process.env.E2E_REPORT_BUCKET ?? "goa-e2e-reports";
const LOCALSTACK_CONTAINER = process.env.LOCALSTACK_CONTAINER ?? "goa-localstack-1";

interface JourneyOutcome {
  journey: string;
  title: string;
  status: "passed" | "failed" | "timedOut" | "skipped" | "interrupted";
  durationMs: number;
  retries: number;
  error?: string;
  attachments: string[];
}

export default class JourneyReporter implements Reporter {
  private startedAt = Date.now();
  private outcomes: JourneyOutcome[] = [];
  private outDir = "";
  private timestamp = "";
  private playwrightVersion = "unknown";

  onBegin(config: FullConfig): void {
    this.startedAt = Date.now();
    this.playwrightVersion = config.version ?? "unknown";
    // Basic ISO with punctuation stripped -- an S3 prefix with colons in it is
    // legal but miserable to type into the CLI.
    this.timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    this.outDir = join(process.cwd(), "test-results", "journeys", this.timestamp);
    mkdirSync(this.outDir, { recursive: true });
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    // The journey name is the top-level describe title, which is what the AC
    // means by "pass or fail per journey".
    const journey = test.parent?.title || test.title;

    const attachments: string[] = [];
    for (const attachment of result.attachments) {
      // Step timings arrive as in-memory attachments from the worker process,
      // which is the only way they can cross into this one.
      if (attachment.name === STEP_ATTACHMENT && attachment.body) {
        try {
          recordStep(JSON.parse(attachment.body.toString("utf-8")));
        } catch (error) {
          console.warn(`could not parse a step timing: ${error}`);
        }
        continue;
      }
      if (!attachment.path || !existsSync(attachment.path)) continue;
      // Screenshots and traces only on failure -- a passing run does not need
      // 40MB of traces uploaded, and the AC asks for them "on any failure".
      const isEvidence =
        attachment.name === "screenshot" ||
        attachment.name === "trace" ||
        attachment.name === "video";
      if (!isEvidence) continue;
      if (result.status === "passed" && attachment.name !== "trace") continue;

      const destination = join(
        this.outDir,
        `${journey.replace(/[^\w.-]+/g, "_")}--${basename(attachment.path)}`,
      );
      try {
        copyFileSync(attachment.path, destination);
        attachments.push(basename(destination));
      } catch (error) {
        console.warn(`could not collect ${attachment.path}: ${error}`);
      }
    }

    this.outcomes.push({
      journey,
      title: test.title,
      status: result.status,
      durationMs: result.duration,
      retries: result.retry,
      // First line only: a full Playwright error with its ANSI snippet is
      // hundreds of lines and unreadable inside a JSON summary. The trace has
      // the detail.
      error: result.error?.message?.split("\n")[0],
      attachments,
    });
  }

  async onEnd(result: FullResult): Promise<void> {
    const totalDurationMs = Date.now() - this.startedAt;

    const { pushed, ok: metricsOk } = await pushCollectedSteps();

    // Loud on purpose. A run that emits zero step timings is how this pipeline
    // failed the first time -- the worker collected them and the reporter, in a
    // different process, pushed an empty array and reported success. Silence
    // there is indistinguishable from working.
    if (pushed === 0 && this.outcomes.length > 0) {
      console.warn(
        "GOA-030: no goa_e2e_step_duration_ms samples were collected, although " +
          `${this.outcomes.length} test(s) ran. The step() helper attaches timings ` +
          `as "${STEP_ATTACHMENT}"; if that name or the attachment channel changed, ` +
          "this metric is silently empty.",
      );
    }

    const summary = {
      ticket: "GOA-030",
      timestamp: this.timestamp,
      status: result.status,
      totalDurationMs,
      totalDurationSeconds: Math.round(totalDurationMs / 1000),
      playwrightVersion: this.playwrightVersion,
      environment: {
        // Stated rather than assumed: every number in this file describes a
        // local docker-compose stack, not the staging environment the ticket
        // was written against, because there is no staging environment.
        target: "local docker-compose via Gateway",
        gatewayUrl: process.env.GATEWAY_URL ?? "http://localhost:8080",
        baseUrl: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
        staging: false,
        stagingUnavailableReason:
          "GOA-021 never received AWS credentials; deploy-staging.yml paused 2026-07-27",
      },
      journeys: this.outcomes.map((outcome) => ({
        journey: outcome.journey,
        title: outcome.title,
        // The AC's "pass or fail per journey". Kept alongside the raw status so
        // a skip is never silently counted as a pass.
        passed: outcome.status === "passed",
        status: outcome.status,
        durationMs: outcome.durationMs,
        retries: outcome.retries,
        error: outcome.error,
        artefacts: outcome.attachments,
      })),
      stepDurations: collectedSamples(),
      metrics: {
        name: "goa_e2e_step_duration_ms",
        labels: ["journey", "step"],
        backend: "prometheus pushgateway",
        backendReason: "no CloudWatch on this project; see environment.staging",
        samplesPushed: pushed,
        pushSucceeded: metricsOk,
      },
    };

    const summaryPath = join(this.outDir, "summary.json");
    writeFileSync(summaryPath, JSON.stringify(summary, null, 2), "utf-8");
    console.log(`\nGOA-030 summary: ${summaryPath}`);

    this.uploadToS3();
  }

  /**
   * Copies the run directory into the LocalStack bucket.
   *
   * Shelled through `docker exec` + `awslocal` deliberately: it is the tool the
   * rest of this repo already uses against LocalStack (see
   * infra/localstack/init/), it needs no AWS SDK dependency in the frontend's
   * package.json, and it fails visibly rather than silently resolving to real
   * AWS the way a misconfigured SDK endpoint does.
   */
  private uploadToS3(): void {
    const prefix = `s3://${BUCKET}/tests/e2e/${this.timestamp}/`;
    try {
      execFileSync(
        "docker",
        [
          "exec",
          "-i",
          LOCALSTACK_CONTAINER,
          "sh",
          "-c",
          `mkdir -p /tmp/goa-e2e && rm -rf /tmp/goa-e2e/*`,
        ],
        { stdio: "pipe" },
      );
      execFileSync(
        "docker",
        ["cp", `${this.outDir}/.`, `${LOCALSTACK_CONTAINER}:/tmp/goa-e2e/`],
        { stdio: "pipe" },
      );
      execFileSync(
        "docker",
        [
          "exec",
          "-i",
          LOCALSTACK_CONTAINER,
          "awslocal",
          "s3",
          "cp",
          "/tmp/goa-e2e/",
          prefix,
          "--recursive",
        ],
        { stdio: "pipe" },
      );
      console.log(`GOA-030 artefacts uploaded: ${prefix}`);
    } catch (error) {
      // Not fatal. The artefacts are on disk either way, and a failed upload
      // must not change a journey's verdict.
      const detail = error instanceof Error ? error.message : String(error);
      console.warn(
        `GOA-030: could not upload artefacts to ${prefix} (${detail.split("\n")[0]}). ` +
          `They remain at ${this.outDir}.`,
      );
    }
  }
}

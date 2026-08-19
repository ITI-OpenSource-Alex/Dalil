"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { AlertCircle, FileText, Sparkles } from "lucide-react";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";
import { sanitizeErrorMessage } from "@/lib/chat-sanitize";
import { getLatestCv, type CvLatestResponse } from "@/lib/cv-api";
import { isSubscriptionRequiredError } from "@/lib/subscription";
import {
  cancelProgramCvReview,
  CV_REVIEW_SECTION_COUNT,
  getEmptyProgramCvReviewSnapshot,
  getProgramCvReviewSnapshot,
  programCvReviewKey,
  startProgramCvReview,
  subscribeProgramCvReview,
} from "@/lib/program-cv-review-store";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  Progress,
  Spinner,
  Text,
} from "@/components/ui";

const PROCESSING_POLL_MS = 5000;

export default function ProgramCvRecommendations({
  programId,
  programName,
  country,
}: {
  programId: string;
  programName?: string | null;
  country?: string | null;
}) {
  const upgrade = useUpgradePrompt();
  const [cv, setCv] = useState<CvLatestResponse | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const reviewKey =
    cv?.status === "ready" ? programCvReviewKey(programId, cv.s3Key) : null;
  const subscribeToReview = useCallback(
    (listener: () => void) => subscribeProgramCvReview(reviewKey, listener),
    [reviewKey],
  );
  const getReviewSnapshot = useCallback(
    () => getProgramCvReviewSnapshot(reviewKey),
    [reviewKey],
  );
  const review = useSyncExternalStore(
    subscribeToReview,
    getReviewSnapshot,
    getEmptyProgramCvReviewSnapshot,
  );
  const {
    reviewing,
    sections,
    overallScore,
    partialReview,
    notice: reviewNotice,
    failure: reviewFailure,
    startedAt,
  } = review;
  const reviewError =
    reviewFailure === null
      ? null
      : typeof reviewFailure === "string"
        ? reviewFailure
        : isSubscriptionRequiredError(reviewFailure)
          ? "Programme-specific CV recommendations are part of Dalil Pro."
          : sanitizeErrorMessage(
              reviewFailure instanceof Error ? reviewFailure.message : undefined,
            );

  const loadCv = useCallback(async () => {
    try {
      setCv(await getLatestCv());
      setLoadError(null);
    } catch (error) {
      setLoadError(
        sanitizeErrorMessage(error instanceof Error ? error.message : undefined),
      );
    }
  }, []);

  useEffect(() => {
    void loadCv();
  }, [loadCv]);

  useEffect(() => {
    if (cv?.status !== "processing") return;
    const timer = setInterval(() => void loadCv(), PROCESSING_POLL_MS);
    return () => clearInterval(timer);
  }, [cv?.status, cv?.cvId, loadCv]);

  useEffect(() => {
    if (!reviewing || startedAt === null) return;
    const updateElapsed = () =>
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    updateElapsed();
    const timer = setInterval(updateElapsed, 1000);
    return () => clearInterval(timer);
  }, [reviewing, startedAt]);

  useEffect(() => {
    if (reviewFailure && isSubscriptionRequiredError(reviewFailure)) {
      upgrade.handle(reviewFailure, "cv-review");
    }
  }, [reviewFailure, upgrade]);

  function generateRecommendations() {
    if (!cv || cv.status !== "ready" || !reviewKey || reviewing) return;
    startProgramCvReview({ key: reviewKey, cvS3Key: cv.s3Key, programId });
  }

  function cancelReview() {
    cancelProgramCvReview(reviewKey);
  }

  const targetLabel = programName || "this programme";

  return (
    <Card
      data-testid="program-cv-recommendations"
      padding="lg"
      className="print-hidden"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
              <Icon icon={FileText} size="sm" />
            </span>
            <div>
              <Heading as="h2" size="md">
                CV recommendations
              </Heading>
              <Text size="sm" tone="muted">
                Tailored to {targetLabel}{country ? ` in ${country}` : ""}.
              </Text>
            </div>
          </div>
        </div>

        {cv?.status === "ready" && (
          <Button
            size="sm"
            leadingIcon={reviewing ? undefined : Sparkles}
            disabled={reviewing}
            onClick={generateRecommendations}
            className="shrink-0"
          >
            {reviewing
              ? `Reviewing ${sections.length} of ${CV_REVIEW_SECTION_COUNT}`
              : overallScore === null
                ? "Review for this programme"
                : "Run again"}
          </Button>
        )}
      </div>

      <div className="mt-6">
        {cv === undefined && !loadError && (
          <div className="flex items-center gap-3 py-2" aria-busy="true">
            <Spinner size="sm" />
            <Text size="sm" tone="muted">
              Checking your profile CV&hellip;
            </Text>
          </div>
        )}

        {loadError && (
          <Alert
            tone="danger"
            title="We couldn't check your profile CV"
            actions={
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setLoadError(null);
                    void loadCv();
                  }}
                >
                  Retry
                </Button>
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/profile?tab=cv">Manage CV</Link>
                </Button>
              </>
            }
          >
            The CV service is temporarily unavailable. Your checklist is still usable.
          </Alert>
        )}

        {cv === null && (
          <div className="flex flex-col gap-3 rounded-card border border-border bg-canvas-subtle p-4 sm:flex-row sm:items-center sm:justify-between">
            <Text size="sm" tone="muted">
              Upload one CV in your profile, then reuse it for every programme.
            </Text>
            <Button variant="secondary" size="sm" asChild>
              <Link href="/profile?tab=cv">Add CV to profile</Link>
            </Button>
          </div>
        )}

        {cv?.status === "processing" && (
          <Alert tone="warning" announce="polite">
            Your profile CV is still being prepared. Recommendations will unlock
            here automatically when it is ready.
          </Alert>
        )}

        {cv?.status === "failed" && (
          <div className="flex flex-col gap-3 rounded-card border border-danger-border bg-danger-subtle p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <Icon icon={AlertCircle} size="sm" className="mt-0.5 text-danger" />
              <Text size="sm" className="text-danger-fg">
                Your profile CV could not be processed. Replace it before requesting
                recommendations.
              </Text>
            </div>
            <Button variant="secondary" size="sm" asChild>
              <Link href="/profile?tab=cv">Replace CV</Link>
            </Button>
          </div>
        )}

        {cv?.status === "ready" && sections.length === 0 && !reviewing && (
          <Text size="sm" tone="muted">
            Uses <span className="font-medium text-fg">{cv.originalFilename}</span> from
            your profile and the verified requirements for this programme.
          </Text>
        )}

        {reviewError && (
          <Alert tone="danger" announce="assertive" className="mt-4">
            {reviewError}
          </Alert>
        )}

        {reviewNotice && (
          <Alert tone="warning" announce="polite" className="mt-4">
            {reviewNotice}
          </Alert>
        )}

        {reviewing && (
          <div
            className="mt-4 rounded-card border border-brand-border bg-brand-subtle p-4"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex min-w-0 items-start gap-3">
                <Spinner size="sm" className="mt-0.5 shrink-0" />
                <div>
                  <Text size="sm" weight="semibold">
                    {sections.length === 0
                      ? "Reading your CV and programme requirements"
                      : "Building your programme-specific recommendations"}
                  </Text>
                  <Text size="sm" tone="muted">
                    Results appear below as each check finishes.
                  </Text>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={cancelReview}>
                Cancel
              </Button>
            </div>
            <Progress
              className="mt-4"
              value={sections.length}
              max={CV_REVIEW_SECTION_COUNT}
              label="CV review progress"
              valueText={`${sections.length} of ${CV_REVIEW_SECTION_COUNT} checks complete`}
              showValue
              size="sm"
            />
            <Text size="sm" tone="muted" className="mt-2 tabular-nums">
              {elapsedSeconds}s elapsed · AI review can take 1–2 minutes
            </Text>
          </div>
        )}

        {sections.length > 0 && (
          <div className="mt-8 space-y-5 border-t border-border pt-6">
            {overallScore !== null && (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Badge tone={partialReview ? "warning" : "brand"} pill>
                  {partialReview ? "Partial fit" : "Programme fit"} {overallScore}/100
                </Badge>
                <ExplainWithDalilButton
                  context={{
                    kind: "cv_review",
                    title: `your CV recommendations for ${targetLabel}`,
                    subjectId: programId,
                    summary: country || undefined,
                    facts: compactFacts([
                      fact("Programme", targetLabel),
                      fact("Country", country),
                      fact("Overall CV score", `${overallScore}/100`),
                      ...sections.map((section) =>
                        fact(`${section.name} score`, `${section.score}/100`),
                      ),
                    ]),
                    limitations: [
                      "These recommendations support an application but do not predict admission.",
                    ],
                  }}
                  prompt={`Explain my CV recommendations for ${targetLabel}. Which changes matter most for this specific programme and why?`}
                />
              </div>
            )}

            {sections.map((section) => (
              <section
                key={section.name}
                className="rounded-card border border-border bg-canvas-subtle p-5"
              >
                <div className="grid gap-6 lg:grid-cols-[minmax(12rem,0.7fr)_minmax(0,1fr)_minmax(0,1fr)]">
                  <Progress
                    value={section.score}
                    label={section.name}
                    valueText={`${section.score}/100`}
                    showValue
                    tone={
                      section.score >= 70
                        ? "success"
                        : section.score >= 40
                          ? "warning"
                          : "danger"
                    }
                  />
                  <div>
                    <Text size="sm" weight="semibold">
                      What to fix
                    </Text>
                    {section.issues.length > 0 ? (
                      <ul className="mt-2 list-outside list-disc space-y-2 pl-5">
                        {section.issues.map((issue, index) => (
                          <Text
                            as="li"
                            key={`${issue}-${index}`}
                            size="sm"
                            tone="muted"
                          >
                            {issue}
                          </Text>
                        ))}
                      </ul>
                    ) : (
                      <Text size="sm" tone="subtle" className="mt-2">
                        No issues identified.
                      </Text>
                    )}
                  </div>
                  <div>
                    <Text size="sm" weight="semibold">
                      Recommended changes
                    </Text>
                    {section.suggestions.length > 0 ? (
                      <ul className="mt-2 list-outside list-disc space-y-2 pl-5">
                        {section.suggestions.map((suggestion, index) => (
                          <Text as="li" key={`${suggestion}-${index}`} size="sm">
                            {suggestion}
                          </Text>
                        ))}
                      </ul>
                    ) : (
                      <Text size="sm" tone="subtle" className="mt-2">
                        No changes suggested.
                      </Text>
                    )}
                  </div>
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

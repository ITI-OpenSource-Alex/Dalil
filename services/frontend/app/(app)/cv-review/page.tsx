"use client";

import { useState } from "react";
import { History, Sparkles } from "lucide-react";
import { sanitizeErrorMessage } from "@/lib/chat-sanitize";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import {
  streamCvReview,
  type CvLatestResponse,
  type CvReviewSection,
} from "@/lib/cv-api";
import { CvUploadPanel } from "@/components/cv/cv-upload-panel";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Heading,
  Input,
  PageContainer,
  Progress,
  Spinner,
  Text,
} from "@/components/ui";

/**
 * CV Review, standalone (Phase E, docs/IA-REDESIGN-PROPOSAL.md). All CV
 * functionality lives here now: onboarding's CvUploadStep is gone (Phase C
 * removed the onboarding step; this page is where a CV actually gets
 * reviewed). Upload is free-tier; POST /cv/review remains paid, so Start
 * Review always attempts the call and lets the SubscriptionRequiredError
 * from a Free account resolve into the shared upgrade dialog, exactly like
 * Writing Practice and the Exam pages -- there is no client-side tier check
 * gating the button itself.
 *
 * Dropzone + status live in CvUploadPanel (shared with profile embed).
 */
export default function CvReviewPage() {
  const upgrade = useUpgradePrompt();

  const [cv, setCv] = useState<CvLatestResponse | null | undefined>(undefined);

  const [targetCountry, setTargetCountry] = useState("");
  const [targetField, setTargetField] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [sections, setSections] = useState<CvReviewSection[]>([]);
  const [overallScore, setOverallScore] = useState<number | undefined>();

  function clearReviewResults() {
    setSections([]);
    setOverallScore(undefined);
    setReviewError(null);
  }

  async function handleStartReview() {
    if (!cv || cv.status !== "ready") return;
    setReviewing(true);
    setReviewError(null);
    setSections([]);
    setOverallScore(undefined);

    try {
      await streamCvReview(
        { cvS3Key: cv.s3Key, targetCountry, targetField },
        (event) => {
          if (event.type === "section") {
            setSections((prev) => [...prev, event]);
          } else if (event.type === "complete") {
            setSections(event.sections);
            setOverallScore(event.overallScore);
            setReviewing(false);
          } else if (event.type === "error") {
            setReviewError(event.detail);
            setReviewing(false);
          }
        },
      );
    } catch (err) {
      setReviewing(false);
      if (upgrade.handle(err, "cv-review")) {
        setReviewError("CV review is part of GOA Pro — see the upgrade details.");
        return;
      }
      setReviewError(sanitizeErrorMessage(err instanceof Error ? err.message : undefined));
    }
  }

  return (
    <PageContainer size="lg">
      <div className="mb-8">
        <Badge tone="brand" pill>
          CV Review
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          CV Review
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Upload your CV and get structured, AI-reviewed feedback aimed at
          admissions committees.
        </Text>
      </div>

      <div className="space-y-6">
        <CvUploadPanel onCvChange={setCv} onUploadStart={clearReviewResults} />

        <Card>
          <Heading as="h2" size="xs" className="mb-4">
            Start review
          </Heading>

          {cv?.status !== "ready" ? (
            <Text size="sm" tone="muted">
              {cv?.status === "processing"
                ? "Your CV is still being processed — review will be available once it's ready."
                : cv?.status === "failed"
                  ? "The last upload could not be processed. Replace it with another file to try again."
                  : "Upload a CV above to unlock review."}
            </Text>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Target country" required>
                  <Input
                    value={targetCountry}
                    onChange={(e) => setTargetCountry(e.target.value)}
                    placeholder="e.g. Germany"
                  />
                </Field>
                <Field label="Target field of study" required>
                  <Input
                    value={targetField}
                    onChange={(e) => setTargetField(e.target.value)}
                    placeholder="e.g. Computer Science"
                  />
                </Field>
              </div>

              <Button
                leadingIcon={Sparkles}
                loading={reviewing}
                loadingLabel="Reviewing your CV"
                disabled={!targetCountry.trim() || !targetField.trim()}
                onClick={handleStartReview}
              >
                Start CV Review
              </Button>

              {reviewError && (
                <Alert tone="danger" announce="assertive">
                  {reviewError}
                </Alert>
              )}
            </div>
          )}
        </Card>

        {(sections.length > 0 || reviewing) && (
          <Card>
            <div className="mb-4 flex items-center justify-between gap-3">
              <Heading as="h2" size="xs">
                Review results
              </Heading>
              {overallScore !== undefined && (
                <Badge tone="brand" pill>
                  Overall score {overallScore}/100
                </Badge>
              )}
            </div>

            {sections.length === 0 && reviewing && (
              <div className="flex items-center gap-3 py-4">
                <Spinner size="sm" />
                <Text size="sm" tone="muted">
                  Reviewing your CV section by section&hellip;
                </Text>
              </div>
            )}

            <div className="space-y-5">
              {sections.map((section) => (
                <div key={section.name}>
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
                  {section.issues.length > 0 && (
                    <ul className="mt-2 list-inside list-disc space-y-1">
                      {section.issues.map((issue) => (
                        <Text as="li" key={issue} size="sm" tone="muted">
                          {issue}
                        </Text>
                      ))}
                    </ul>
                  )}
                  {section.suggestions.length > 0 && (
                    <ul className="mt-2 list-inside list-disc space-y-1">
                      {section.suggestions.map((suggestion) => (
                        <Text as="li" key={suggestion} size="sm">
                          {suggestion}
                        </Text>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card>
          <Heading as="h2" size="xs" className="mb-4">
            Review history
          </Heading>
          {/* The backend has no endpoint for past review results -- only the
              most recent CV upload (GET /cv/latest) and a content-keyed cache
              that is not addressable as a list. Rather than invent history
              data, this is an honest empty state until that endpoint exists. */}
          <EmptyState
            icon={History}
            title="Review history isn't available yet"
            description="Past CV reviews aren't stored for later reference. Run a new review any time above."
            size="sm"
          />
        </Card>
      </div>
    </PageContainer>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  History,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { sanitizeErrorMessage } from "@/lib/chat-sanitize";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import {
  getLatestCv,
  streamCvReview,
  uploadCv,
  type CvLatestResponse,
  type CvReviewSection,
} from "@/lib/cv-api";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Heading,
  Icon,
  Input,
  PageContainer,
  Progress,
  Spinner,
  Text,
} from "@/components/ui";

const MAX_SIZE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

// CV status is "processing" right after upload until an async pipeline
// (S3 -> SQS -> the CV processor) extracts its text -- see
// services/writing/app/routers/cvs.py. This page polls GET /cv/latest while
// that is in flight rather than requiring a manual refresh.
const POLL_INTERVAL_MS = 4000;

/**
 * CV Review, standalone (Phase E, docs/IA-REDESIGN-PROPOSAL.md). All CV
 * functionality lives here now: onboarding's CvUploadStep is gone (Phase C
 * removed the onboarding step; this page is where a CV actually gets
 * reviewed). Upload is free-tier; POST /cv/review remains paid, so Start
 * Review always attempts the call and lets the SubscriptionRequiredError
 * from a Free account resolve into the shared upgrade dialog, exactly like
 * Writing Practice and the Exam pages -- there is no client-side tier check
 * gating the button itself.
 */
export default function CvReviewPage() {
  const upgrade = useUpgradePrompt();

  const [cv, setCv] = useState<CvLatestResponse | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);

  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [targetCountry, setTargetCountry] = useState("");
  const [targetField, setTargetField] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [sections, setSections] = useState<CvReviewSection[]>([]);
  const [overallScore, setOverallScore] = useState<number | undefined>();

  async function loadLatest() {
    try {
      const latest = await getLatestCv();
      setCv(latest);
      setLoadError(null);
    } catch (err) {
      setLoadError(sanitizeErrorMessage(err instanceof Error ? err.message : undefined));
    }
  }

  useEffect(() => {
    loadLatest();
  }, []);

  // Poll while the extraction pipeline is still working on the current CV.
  useEffect(() => {
    if (cv?.status !== "processing") return;
    const timer = setInterval(loadLatest, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [cv?.status]);

  function validate(candidate: File): string | null {
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      return "Only PDF, DOC or DOCX files are supported.";
    }
    if (candidate.size > MAX_SIZE_BYTES) return "File is too large — the limit is 10 MB.";
    return null;
  }

  async function startUpload(selected: File) {
    const error = validate(selected);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    setUploadError(null);
    setUploading(true);
    setSections([]);
    setOverallScore(undefined);
    setReviewError(null);

    try {
      const result = await uploadCv(selected);
      setCv({
        cvId: result.cvId,
        s3Key: result.s3Key,
        originalFilename: selected.name,
        status: result.status,
        uploadedAt: new Date().toISOString(),
      });
      setReplacing(false);
    } catch (err) {
      setUploadError(sanitizeErrorMessage(err instanceof Error ? err.message : undefined));
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) void startUpload(dropped);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) void startUpload(selected);
    e.target.value = "";
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

  const showDropzone = cv === null || replacing;

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
        {loadError && (
          <Alert tone="danger" announce="assertive">
            {loadError}
          </Alert>
        )}

        <Card>
          <div className="mb-4 flex items-center justify-between gap-3">
            <Heading as="h2" size="xs">
              Your CV
            </Heading>
            {cv && cv !== null && !showDropzone && (
              <Button variant="ghost" size="sm" onClick={() => setReplacing(true)}>
                Replace
              </Button>
            )}
          </div>

          {cv === undefined && (
            <div className="flex items-center gap-3 py-6" aria-busy="true" aria-label="Loading">
              <Spinner size="sm" />
              <Text size="sm" tone="muted">
                Checking for an existing CV&hellip;
              </Text>
            </div>
          )}

          {cv !== undefined && showDropzone && (
            <CvDropzone
              isDragging={isDragging}
              setIsDragging={setIsDragging}
              onDrop={handleDrop}
              onFileChange={handleFileChange}
              fileInputRef={fileInputRef}
              uploading={uploading}
              onCancelReplace={cv !== null ? () => setReplacing(false) : undefined}
            />
          )}

          {validationError && (
            <Alert tone="danger" announce="assertive" className="mt-4">
              {validationError}
            </Alert>
          )}
          {uploadError && (
            <Alert tone="danger" announce="assertive" className="mt-4">
              {uploadError}
            </Alert>
          )}

          {cv !== undefined && cv !== null && !showDropzone && (
            <CvStatusCard cv={cv} />
          )}
        </Card>

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

function CvDropzone({
  isDragging,
  setIsDragging,
  onDrop,
  onFileChange,
  fileInputRef,
  uploading,
  onCancelReplace,
}: {
  isDragging: boolean;
  setIsDragging: (value: boolean) => void;
  onDrop: (e: React.DragEvent) => void;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  uploading: boolean;
  onCancelReplace?: () => void;
}) {
  if (uploading) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-card border border-border bg-canvas-subtle p-8 text-center">
        <Spinner size="md" />
        <Text size="sm" tone="muted">
          Uploading your CV&hellip;
        </Text>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        aria-label="Upload your CV as a PDF, DOC or DOCX, up to 10 megabytes"
        className={cn(
          "flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed p-8 text-center transition-colors duration-120 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted",
          isDragging
            ? "border-brand bg-brand-subtle"
            : "border-border bg-surface hover:border-brand-border hover:bg-canvas-subtle",
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={onFileChange}
          className="hidden"
        />
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
          <Icon icon={Upload} size="md" />
        </span>
        <p className="mt-3 text-sm font-semibold text-fg">
          Drag &amp; drop your CV here
        </p>
        <p className="mt-1 text-sm text-fg-subtle">PDF, DOC or DOCX, up to 10 MB</p>
        <Button variant="secondary" size="sm" className="mt-4" tabIndex={-1}>
          Browse files
        </Button>
      </div>
      {onCancelReplace && (
        <Button variant="ghost" size="sm" leadingIcon={X} onClick={onCancelReplace}>
          Cancel
        </Button>
      )}
    </div>
  );
}

function CvStatusCard({ cv }: { cv: CvLatestResponse }) {
  if (cv.status === "processing") {
    return (
      <div className="flex items-center gap-3 rounded-card border border-border bg-canvas-subtle p-5">
        <Spinner size="sm" />
        <div>
          <Text size="sm" className="font-semibold text-fg">
            {cv.originalFilename}
          </Text>
          <Text size="sm" tone="muted">
            Processing&hellip; this can take a moment.
          </Text>
        </div>
      </div>
    );
  }

  if (cv.status === "failed") {
    return (
      <div className="flex items-start gap-3 rounded-card border border-danger-border bg-danger-subtle p-5">
        <Icon icon={AlertCircle} size="sm" className="mt-0.5 shrink-0 text-danger" />
        <div className="min-w-0">
          <Text size="sm" className="font-semibold text-danger-fg">
            {cv.originalFilename}
          </Text>
          <Text size="sm" className="text-danger-fg/90">
            {cv.errorMessage || "This CV could not be processed."}
          </Text>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-card border border-success-border bg-success-subtle p-5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-success text-white">
        <Icon icon={CheckCircle2} size="sm" />
      </span>
      <div className="min-w-0">
        <Text size="sm" className="truncate font-semibold text-success-fg">
          {cv.originalFilename}
        </Text>
        <Text size="sm" className="text-success-fg/80">
          Ready for review
        </Text>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  RefreshCw,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { sanitizeErrorMessage } from "@/lib/chat-sanitize";
import {
  getLatestCv,
  uploadCv,
  type CvLatestResponse,
} from "@/lib/cv-api";
import {
  Alert,
  Button,
  Card,
  Heading,
  Icon,
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
// services/writing/app/routers/cvs.py. This panel polls GET /cv/latest while
// that is in flight rather than requiring a manual refresh.
const POLL_INTERVAL_MS = 4000;
const DELAYED_POLL_INTERVAL_MS = 15000;
export const CV_PROCESSING_DELAY_MS = 2 * 60 * 1000;

export function isCvProcessingDelayed(
  cv: Pick<CvLatestResponse, "status" | "uploadedAt">,
  now: number,
) {
  if (cv.status !== "processing" || !now) return false;
  const uploadedAt = Date.parse(cv.uploadedAt);
  return Number.isFinite(uploadedAt) && now - uploadedAt >= CV_PROCESSING_DELAY_MS;
}

export function cvProcessingElapsedSeconds(
  cv: Pick<CvLatestResponse, "uploadedAt">,
  now: number,
): number {
  const uploadedAt = Date.parse(cv.uploadedAt);
  if (!Number.isFinite(uploadedAt) || !now) return 0;
  return Math.max(0, Math.floor((now - uploadedAt) / 1000));
}

export function formatCvProcessingElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
}

export type CvUploadPanelProps = {
  /** Notifies the parent whenever the loaded/uploaded CV changes. */
  onCvChange?: (cv: CvLatestResponse | null | undefined) => void;
  /** Fired when a new upload begins (e.g. clear review results on cv-review). */
  onUploadStart?: () => void;
};

/**
 * Profile-owned CV dropzone and processing status.
 * Owns load, upload, validation, replace, and processing poll.
 */
export function CvUploadPanel({
  onCvChange,
  onUploadStart,
}: CvUploadPanelProps) {
  const [cv, setCv] = useState<CvLatestResponse | null | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [replacing, setReplacing] = useState(false);

  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [processingClock, setProcessingClock] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const loadInFlightRef = useRef(false);

  function updateCv(next: CvLatestResponse | null | undefined) {
    setCv(next);
    onCvChange?.(next);
  }

  async function loadLatest(manual = false) {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    if (manual) setCheckingStatus(true);
    try {
      const latest = await getLatestCv();
      updateCv(latest);
      setLoadError(null);
    } catch (err) {
      setLoadError(
        "We couldn't check your saved CV. You can retry or upload a replacement below.",
      );
    } finally {
      loadInFlightRef.current = false;
      if (manual) setCheckingStatus(false);
    }
  }

  useEffect(() => {
    void loadLatest();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only initial load
  }, []);

  // Poll while the extraction pipeline is still working on the current CV.
  useEffect(() => {
    if (cv?.status !== "processing") return;
    setProcessingClock(Date.now());
    const clock = setInterval(() => setProcessingClock(Date.now()), 10000);
    return () => clearInterval(clock);
  }, [cv?.status, cv?.cvId]);

  const processingDelayed = cv
    ? isCvProcessingDelayed(cv, processingClock)
    : false;
  const processingElapsedSeconds = cv
    ? cvProcessingElapsedSeconds(cv, processingClock)
    : 0;

  // Poll quickly for a normal job, then back off if processing is delayed.
  useEffect(() => {
    if (cv?.status !== "processing") return;
    const timer = setInterval(() => {
      void loadLatest();
    }, processingDelayed ? DELAYED_POLL_INTERVAL_MS : POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- polling follows current CV state
  }, [cv?.status, cv?.cvId, processingDelayed]);

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
    onUploadStart?.();

    try {
      const result = await uploadCv(selected);
      updateCv({
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

  const showDropzone = cv === null || replacing || (cv === undefined && !!loadError);

  return (
    <div className="space-y-4">
      {loadError && (
        <Alert
          tone="danger"
          announce="assertive"
          title="Your saved CV is temporarily unavailable"
          actions={
            <Button
              variant="secondary"
              size="sm"
              leadingIcon={RefreshCw}
              onClick={() => {
                setLoadError(null);
                void loadLatest(true);
              }}
            >
              Retry
            </Button>
          }
        >
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

        {cv === undefined && !loadError && (
          <div className="flex items-center gap-3 py-6" aria-busy="true" aria-label="Loading">
            <Spinner size="sm" />
            <Text size="sm" tone="muted">
              Checking for an existing CV&hellip;
            </Text>
          </div>
        )}

        {showDropzone && (
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
          <CvStatusCard
            cv={cv}
            processingDelayed={processingDelayed}
            elapsedSeconds={processingElapsedSeconds}
            checkingStatus={checkingStatus}
            onCheckStatus={() => void loadLatest(true)}
          />
        )}

      </Card>
    </div>
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

function CvStatusCard({
  cv,
  processingDelayed,
  elapsedSeconds,
  checkingStatus,
  onCheckStatus,
}: {
  cv: CvLatestResponse;
  processingDelayed: boolean;
  elapsedSeconds: number;
  checkingStatus: boolean;
  onCheckStatus: () => void;
}) {
  if (cv.status === "processing") {
    return (
      <div
        className={cn(
          "rounded-card border p-5",
          processingDelayed
            ? "border-warning-border bg-warning-subtle"
            : "border-brand-border bg-brand-subtle",
        )}
        role="status"
        aria-live="polite"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            {processingDelayed ? (
              <Icon
                icon={Clock3}
                size="sm"
                className="mt-0.5 shrink-0 text-warning-fg"
              />
            ) : (
              <Spinner size="sm" className="mt-0.5 shrink-0" />
            )}
            <div className="min-w-0">
              <Text size="sm" className="truncate font-semibold text-fg">
                {cv.originalFilename}
              </Text>
              <Text size="sm" tone="muted">
                {processingDelayed
                  ? "This is taking longer than usual, but processing is still active."
                  : "Extracting your CV and organizing its details."}
              </Text>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={checkingStatus ? undefined : RefreshCw}
            disabled={checkingStatus}
            onClick={onCheckStatus}
            className="shrink-0"
          >
            {checkingStatus ? "Checking…" : "Check now"}
          </Button>
        </div>

        <ol className="mt-5 grid gap-2 text-sm sm:grid-cols-3" aria-label="CV extraction progress">
          <li className="flex items-center gap-2 font-medium text-success-fg">
            <Icon icon={CheckCircle2} size="xs" />
            Upload received
          </li>
          <li className="flex items-center gap-2 font-medium text-brand-fg">
            <Spinner size="xs" />
            Extracting details
          </li>
          <li className="flex items-center gap-2 text-fg-subtle">
            <span className="h-2 w-2 rounded-full border border-border-strong" />
            Ready for recommendations
          </li>
        </ol>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <Text size="sm" tone="muted" className="tabular-nums">
            {formatCvProcessingElapsed(elapsedSeconds)} elapsed
          </Text>
          <Text size="sm" tone="muted">
            You can leave this tab — we&apos;ll keep processing automatically.
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

"use client";

import { useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, FileText, Upload, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { authApi, apiErrorMessage, isSubscriptionRequired } from "@/lib/api";
import { subscriptionErrorFromAxios } from "@/lib/subscription";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import { Alert, Button, Heading, Icon, Progress, Text } from "@/components/ui";

interface CvUploadStepProps {
  onComplete: (cvData: { fileName: string; skipped: boolean } | null) => void | Promise<void>;
  onBack: () => void;
  /** True while the wizard's own PUT /api/profile call (triggered after this
   * step) is in flight, so the Finish button reflects that too. */
  finishing: boolean;
}

const MAX_SIZE_BYTES = 10 * 1024 * 1024;

type Status = "idle" | "uploading" | "uploaded" | "upgrade-required" | "error";

export default function CvUploadStep({ onComplete, onBack, finishing }: CvUploadStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const upgrade = useUpgradePrompt();

  function validate(candidate: File): string | null {
    if (candidate.type !== "application/pdf") return "Only PDF files are supported.";
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
    setFile(selected);
    setStatus("uploading");
    setProgress(0);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await authApi.uploadCv(selected, { onProgress: setProgress, signal: controller.signal });
      setStatus("uploaded");
    } catch (err) {
      if (controller.signal.aborted) {
        setStatus("idle");
        setFile(null);
        return;
      }
      if (isSubscriptionRequired(err)) {
        setStatus("upgrade-required");
        // The inline panel below still explains that this step is optional --
        // the dialog is what makes the paywall itself read the same here as it
        // does everywhere else in the app.
        const paid = subscriptionErrorFromAxios(err, "cv-review");
        if (paid) upgrade.handle(paid);
      } else {
        setUploadError(apiErrorMessage(err) ?? "Upload failed. Please try again.");
        setStatus("error");
      }
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (status !== "idle" && status !== "error") return;
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) void startUpload(dropped);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) void startUpload(selected);
    e.target.value = "";
  }

  function reset() {
    abortRef.current?.abort();
    setFile(null);
    setProgress(0);
    setStatus("idle");
    setValidationError(null);
    setUploadError(null);
  }

  const dropzoneInteractive = status === "idle" || status === "error";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Heading as="h2" size="md">
            Upload your latest CV
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Optional, but unlocks personalised programme ranking and CV
            review.
          </Text>
        </div>
        {dropzoneInteractive && !file && (
          <Button variant="ghost" size="sm" onClick={() => onComplete({ fileName: "", skipped: true })}>
            Skip step
          </Button>
        )}
      </div>

      {dropzoneInteractive && (
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
          onDrop={handleDrop}
          aria-label="Upload your CV as a PDF, up to 10 megabytes"
          className={cn(
            "flex min-h-55 cursor-pointer flex-col items-center justify-center rounded-card border-2 border-dashed p-8 text-center transition-colors duration-120 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted",
            isDragging
              ? "border-brand bg-brand-subtle"
              : "border-border bg-surface hover:border-brand-border hover:bg-canvas-subtle",
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileChange}
            className="hidden"
          />
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
            <Icon icon={Upload} size="md" />
          </span>
          <p className="mt-3 text-sm font-semibold text-fg">
            Drag &amp; drop your resume here
          </p>
          <p className="mt-1 text-sm text-fg-subtle">
            PDF only, up to 10 MB
          </p>
          <Button variant="secondary" size="sm" className="mt-4" tabIndex={-1}>
            Browse files
          </Button>
        </div>
      )}

      {validationError && (
        <Alert tone="danger" announce="assertive">
          {validationError}
        </Alert>
      )}

      {status === "uploading" && (
        <div className="flex flex-col gap-3 rounded-card border border-border bg-canvas-subtle p-5">
          <div className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-fg">
              <Icon icon={FileText} size="sm" className="shrink-0 text-fg-subtle" />
              <span className="truncate">{file?.name}</span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="Cancel upload"
              onClick={() => abortRef.current?.abort()}
            >
              <Icon icon={X} size="sm" />
            </Button>
          </div>
          <Progress
            value={progress}
            label="Upload progress"
            valueText={`${progress}%`}
            showValue
            tone="brand"
          />
          <Text size="sm" tone="subtle" className="text-center">
            Uploading document to secure storage&hellip;
          </Text>
        </div>
      )}

      {status === "uploaded" && file && (
        <div className="flex items-center justify-between gap-4 rounded-card border border-success-border bg-success-subtle p-5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-success text-white">
              <Icon icon={CheckCircle2} size="sm" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-success-fg">{file.name}</p>
              <p className="text-sm text-success-fg/80">Uploaded successfully</p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={reset}>
            Replace
          </Button>
        </div>
      )}

      {status === "upgrade-required" && (
        <Alert
          tone="info"
          announce="none"
          title="CV review is part of the paid plan"
        >
          You can skip this for now and add your CV anytime from your
          profile — it won&apos;t block matching or your checklist.
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => onComplete({ fileName: "", skipped: true })}>
              Skip for now
            </Button>
            <Button variant="secondary" size="sm" onClick={reset}>
              Choose a different file
            </Button>
          </div>
        </Alert>
      )}

      {status === "error" && uploadError && (
        <Alert tone="danger" announce="assertive">
          {uploadError}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={reset}>
              Try again
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onComplete({ fileName: "", skipped: true })}>
              Skip and finish
            </Button>
          </div>
        </Alert>
      )}

      {/* Finish is always present, not only after a successful upload.
          The CV is explicitly optional, yet the only path off this step
          without one was a small ghost "Skip step" link in the header --
          so a user who simply had no CV to hand saw a wizard with no
          primary action and no obvious way to save the three steps of
          answers they had already given. */}
      <div className="flex flex-col-reverse gap-3 sm:flex-row">
        <Button
          type="button"
          variant="secondary"
          size="lg"
          leadingIcon={ArrowLeft}
          onClick={onBack}
          disabled={status === "uploading" || finishing}
        >
          Back
        </Button>
        <Button
          type="button"
          size="lg"
          fullWidth
          loading={finishing}
          loadingLabel="Saving your profile"
          disabled={status === "uploading"}
          onClick={() =>
            onComplete(
              status === "uploaded" && file
                ? { fileName: file.name, skipped: false }
                : { fileName: "", skipped: true },
            )
          }
        >
          {status === "uploaded" ? "Finish" : "Finish without a CV"}
        </Button>
      </div>
    </div>
  );
}

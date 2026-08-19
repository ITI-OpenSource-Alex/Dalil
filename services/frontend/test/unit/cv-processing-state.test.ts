import { describe, expect, it } from "vitest";
import {
  CV_PROCESSING_DELAY_MS,
  cvProcessingElapsedSeconds,
  formatCvProcessingElapsed,
  isCvProcessingDelayed,
} from "@/components/cv/cv-upload-panel";

describe("CV processing state", () => {
  const uploadedAt = "2026-08-18T01:00:00.000Z";
  const uploadedAtMs = Date.parse(uploadedAt);

  it("keeps a recent upload in the normal processing state", () => {
    expect(
      isCvProcessingDelayed(
        { status: "processing", uploadedAt },
        uploadedAtMs + CV_PROCESSING_DELAY_MS - 1,
      ),
    ).toBe(false);
  });

  it("identifies a processing upload that exceeded the expected time", () => {
    expect(
      isCvProcessingDelayed(
        { status: "processing", uploadedAt },
        uploadedAtMs + CV_PROCESSING_DELAY_MS,
      ),
    ).toBe(true);
  });

  it("never labels a completed upload as delayed", () => {
    expect(
      isCvProcessingDelayed(
        { status: "ready", uploadedAt },
        uploadedAtMs + CV_PROCESSING_DELAY_MS,
      ),
    ).toBe(false);
  });

  it("reports a live elapsed duration without allowing negative time", () => {
    expect(
      cvProcessingElapsedSeconds(
        { uploadedAt },
        uploadedAtMs + 65_900,
      ),
    ).toBe(65);
    expect(formatCvProcessingElapsed(65)).toBe("1m 05s");
    expect(
      cvProcessingElapsedSeconds({ uploadedAt }, uploadedAtMs - 1000),
    ).toBe(0);
  });
});

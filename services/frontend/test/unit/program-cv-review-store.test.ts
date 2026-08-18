import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/cv-api", () => ({
  streamCvReview: vi.fn(),
}));

import { streamCvReview } from "@/lib/cv-api";
import {
  getProgramCvReviewSnapshot,
  startProgramCvReview,
  subscribeProgramCvReview,
} from "@/lib/program-cv-review-store";

describe("program CV review task store", () => {
  afterEach(() => vi.clearAllMocks());

  it("keeps the request running after the mounted view unsubscribes", async () => {
    let finishRequest: (() => void) | undefined;
    let emitEvent: ((event: unknown) => void) | undefined;
    let requestSignal: AbortSignal | undefined;

    vi.mocked(streamCvReview).mockImplementation(async (_params, onEvent, signal) => {
      requestSignal = signal;
      emitEvent = onEvent as (event: unknown) => void;
      await new Promise<void>((resolve) => {
        finishRequest = resolve;
      });
    });

    const key = `program-navigation\u0000cv-${Date.now()}`;
    const unsubscribe = subscribeProgramCvReview(key, () => {});
    startProgramCvReview({
      key,
      cvS3Key: "cvs/user-1/resume.pdf",
      programId: "program-navigation",
    });

    unsubscribe();
    expect(requestSignal?.aborted).toBe(false);

    emitEvent?.({
      type: "complete",
      overallScore: 81,
      sections: [
        { name: "Skills gaps", score: 81, issues: [], suggestions: [] },
      ],
    });
    finishRequest?.();

    await vi.waitFor(() => {
      expect(getProgramCvReviewSnapshot(key).reviewing).toBe(false);
    });
    expect(getProgramCvReviewSnapshot(key).overallScore).toBe(81);
  });
});

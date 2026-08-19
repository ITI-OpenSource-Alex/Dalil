import {
  streamCvReview,
  type CvReviewSection,
} from "@/lib/cv-api";

export const CV_REVIEW_SECTION_COUNT = 5;

export interface ProgramCvReviewSnapshot {
  reviewing: boolean;
  sections: CvReviewSection[];
  overallScore: number | null;
  partialReview: boolean;
  notice: string | null;
  failure: unknown | null;
  startedAt: number | null;
}

interface ReviewEntry {
  snapshot: ProgramCvReviewSnapshot;
  listeners: Set<() => void>;
  controller?: AbortController;
}

const EMPTY_SNAPSHOT: ProgramCvReviewSnapshot = Object.freeze({
  reviewing: false,
  sections: [],
  overallScore: null,
  partialReview: false,
  notice: null,
  failure: null,
  startedAt: null,
});

// Module state survives client-side route changes. The network task therefore
// belongs to the signed-in browser session rather than to one mounted card.
const reviews = new Map<string, ReviewEntry>();

export function programCvReviewKey(programId: string, cvS3Key: string): string {
  return `${programId}\u0000${cvS3Key}`;
}

function ensureEntry(key: string): ReviewEntry {
  let entry = reviews.get(key);
  if (!entry) {
    entry = { snapshot: EMPTY_SNAPSHOT, listeners: new Set() };
    reviews.set(key, entry);
  }
  return entry;
}

function updateEntry(
  key: string,
  update: Partial<ProgramCvReviewSnapshot>,
): void {
  const entry = ensureEntry(key);
  entry.snapshot = { ...entry.snapshot, ...update };
  entry.listeners.forEach((listener) => listener());
}

export function getProgramCvReviewSnapshot(
  key: string | null,
): ProgramCvReviewSnapshot {
  return key ? reviews.get(key)?.snapshot ?? EMPTY_SNAPSHOT : EMPTY_SNAPSHOT;
}

export function getEmptyProgramCvReviewSnapshot(): ProgramCvReviewSnapshot {
  return EMPTY_SNAPSHOT;
}

export function subscribeProgramCvReview(
  key: string | null,
  listener: () => void,
): () => void {
  if (!key) return () => {};
  const entry = ensureEntry(key);
  entry.listeners.add(listener);
  return () => entry.listeners.delete(listener);
}

export function startProgramCvReview({
  key,
  cvS3Key,
  programId,
}: {
  key: string;
  cvS3Key: string;
  programId: string;
}): void {
  const entry = ensureEntry(key);
  if (entry.snapshot.reviewing) return;

  const controller = new AbortController();
  entry.controller = controller;
  updateEntry(key, {
    reviewing: true,
    sections: [],
    overallScore: null,
    partialReview: false,
    notice: null,
    failure: null,
    startedAt: Date.now(),
  });

  void (async () => {
    let receivedTerminalEvent = false;
    try {
      await streamCvReview(
        { cvS3Key, programId },
        (event) => {
          if (event.type === "section") {
            const current = getProgramCvReviewSnapshot(key);
            updateEntry(key, { sections: [...current.sections, event] });
          } else if (event.type === "complete") {
            receivedTerminalEvent = true;
            const partialReview = event.sections.length < CV_REVIEW_SECTION_COUNT;
            updateEntry(key, {
              sections: event.sections,
              overallScore: event.overallScore,
              partialReview,
              notice: partialReview
                ? `${event.sections.length} of ${CV_REVIEW_SECTION_COUNT} checks completed. ` +
                  "The available recommendations are shown below; run it again to retry the missing check."
                : null,
            });
          } else if (event.type === "error") {
            receivedTerminalEvent = true;
            updateEntry(key, { failure: event.detail });
          }
        },
        controller.signal,
      );
      if (!receivedTerminalEvent) {
        updateEntry(key, {
          failure: "The review ended before it returned a result. Please try again.",
        });
      }
    } catch (error) {
      if (controller.signal.aborted) {
        updateEntry(key, {
          notice: "Review stopped. Any recommendations already received are kept below.",
        });
      } else {
        updateEntry(key, { failure: error });
      }
    } finally {
      const current = reviews.get(key);
      if (current?.controller === controller) current.controller = undefined;
      updateEntry(key, { reviewing: false });
    }
  })();
}

export function cancelProgramCvReview(key: string | null): void {
  if (!key) return;
  reviews.get(key)?.controller?.abort();
}

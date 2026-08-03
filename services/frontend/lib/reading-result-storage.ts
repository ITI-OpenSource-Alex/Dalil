import type {
  NormalizedReadingQuestion,
  ReadingSubmitResponse,
} from "@/app/types/reading";

// There is no GET-result endpoint for Reading on the backend — confirmed:
// services/exam/app/api/reading.py only exposes GET /start and
// PUT /:id/submit, and ResultRepository.create only persists
// raw_score/band_score/section_scores, never per_question_result. The full
// submit response (with per_question_result) only ever exists as that PUT
// call's own return value, so it has to be carried forward to the results
// page by the client rather than re-fetched. sessionStorage mirrors the
// app's own existing pattern for passing session state across navigation
// (see active_exam_session in app/exam/page.tsx).
//
// Known limitation this implies (not fixable without a backend change,
// which is out of GOA-055's scope): if sessionStorage is unavailable for
// this session — a different tab/device, or a cleared session — per-question
// results can't be recovered, only the summary raw_score/band_score/
// section_scores via the generic GET /sessions/:id/result.

export interface StoredReadingResult {
  result: ReadingSubmitResponse;
  questions: NormalizedReadingQuestion[];
}

function storageKey(sessionId: string): string {
  return `reading_result_${sessionId}`;
}

export function storeReadingResult(
  sessionId: string,
  data: StoredReadingResult,
): void {
  sessionStorage.setItem(storageKey(sessionId), JSON.stringify(data));
}

export function loadReadingResult(
  sessionId: string,
): StoredReadingResult | null {
  const raw = sessionStorage.getItem(storageKey(sessionId));
  if (!raw) return null;

  try {
    return JSON.parse(raw) as StoredReadingResult;
  } catch {
    return null;
  }
}

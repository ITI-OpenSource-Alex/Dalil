import type {
  ListeningSubmitResponse,
  NormalizedListeningQuestion,
} from "@/app/types/listening";

export interface StoredListeningResult {
  result: ListeningSubmitResponse;
  questions: NormalizedListeningQuestion[];
}

function storageKey(sessionId: string): string {
  return `listening_result_${sessionId}`;
}

export function storeListeningResult(
  sessionId: string,
  data: StoredListeningResult,
): void {
  sessionStorage.setItem(storageKey(sessionId), JSON.stringify(data));
}

export function loadListeningResult(
  sessionId: string,
): StoredListeningResult | null {
  const raw = sessionStorage.getItem(storageKey(sessionId));
  if (!raw) return null;

  try {
    return JSON.parse(raw) as StoredListeningResult;
  } catch {
    return null;
  }
}

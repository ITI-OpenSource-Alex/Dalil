export const READING_SPLIT_DEFAULT = 58;
export const READING_SPLIT_MIN = 40;
export const READING_SPLIT_MAX = 70;
export const READING_SPLIT_STEP = 2;
export const READING_SPLIT_STORAGE_KEY = "reading-exam-split";

export function clampReadingSplitPercent(value: number): number {
  if (!Number.isFinite(value)) return READING_SPLIT_DEFAULT;
  return Math.min(
    READING_SPLIT_MAX,
    Math.max(READING_SPLIT_MIN, Math.round(value)),
  );
}

export function parseReadingSplitPercent(raw: string | null): number {
  if (raw == null || raw.trim() === "") return READING_SPLIT_DEFAULT;
  return clampReadingSplitPercent(Number(raw));
}

export function loadReadingSplitPercent(): number {
  if (typeof window === "undefined") return READING_SPLIT_DEFAULT;
  try {
    return parseReadingSplitPercent(
      window.localStorage.getItem(READING_SPLIT_STORAGE_KEY),
    );
  } catch {
    return READING_SPLIT_DEFAULT;
  }
}

export function saveReadingSplitPercent(percent: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      READING_SPLIT_STORAGE_KEY,
      String(clampReadingSplitPercent(percent)),
    );
  } catch {
    // private mode / quota — ignore
  }
}

/** Map a pointer X into a clamped passage percent of the container. */
export function percentFromClientX(
  clientX: number,
  containerLeft: number,
  containerWidth: number,
): number {
  if (containerWidth <= 0) return READING_SPLIT_DEFAULT;
  return clampReadingSplitPercent(
    ((clientX - containerLeft) / containerWidth) * 100,
  );
}

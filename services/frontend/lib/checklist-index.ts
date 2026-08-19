/**
 * A local index of the checklists this user has opened.
 *
 * The backend has no "list my checklists" route. RAG persists a checklist per
 * (user, programme) and the Gateway exposes GET/PUT for *one* programme id
 * (services/gateway/server.go: /api/checklists/:programId), so the only way to
 * reach a checklist has been to already know the id — which in practice meant
 * clicking through from an opportunity card inside a chat message, and losing
 * it the moment the conversation moved on.
 *
 * This registry is what lets /checklists exist as a page at all. It is a
 * client-side convenience, not a source of truth: the checklist itself, and
 * every checked item, still live server-side. Clearing it loses the shortcut,
 * never the data — reopening the programme restores the same checklist.
 *
 * localStorage rather than sessionStorage, deliberately: an application
 * checklist spans weeks, so it has to survive closing the tab.
 *
 * A proper GET /api/checklists (index) on RAG's side would replace this
 * wholesale, and should. Recorded as a known limitation.
 */

const DEFAULT_STORAGE_KEY = "goa.checklists.index";
const MAX_ENTRIES = 50;

function getStorageKey(userId?: string | null): string {
  if (!userId) return DEFAULT_STORAGE_KEY;
  return `goa.checklists.index.${userId}`;
}

export interface ChecklistIndexEntry {
  programId: string;
  programName: string;
  university: string | null;
  country: string | null;
  /** ISO timestamp of the last time the detail page was opened. */
  lastOpenedAt: string;
  /** Cached progress, refreshed each time the detail page loads. */
  totalItems: number;
  completedItems: number;
}

function isEntry(value: unknown): value is ChecklistIndexEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<ChecklistIndexEntry>;
  return (
    typeof entry.programId === "string" &&
    entry.programId.length > 0 &&
    typeof entry.programName === "string" &&
    typeof entry.lastOpenedAt === "string"
  );
}

export function readChecklistIndex(userId?: string | null): ChecklistIndexEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const key = getStorageKey(userId);
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Filtered per entry rather than rejected wholesale: one corrupt record
    // written by an older build should not hide every other checklist.
    return parsed
      .filter(isEntry)
      .sort((a, b) => b.lastOpenedAt.localeCompare(a.lastOpenedAt));
  } catch {
    return [];
  }
}

function write(entries: ChecklistIndexEntry[], userId?: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const key = getStorageKey(userId);
    window.localStorage.setItem(
      key,
      JSON.stringify(entries.slice(0, MAX_ENTRIES)),
    );
  } catch {
    // Quota or private mode. The registry is a shortcut; losing it is not
    // worth taking the page down for.
  }
}

/**
 * Records (or refreshes) one checklist. Called by the detail page once its
 * data has loaded, so the cached progress is always something that was really
 * observed rather than optimistically assumed.
 */
export function rememberChecklist(
  entry: Omit<ChecklistIndexEntry, "lastOpenedAt">,
  userId?: string | null,
): void {
  const existing = readChecklistIndex(userId).filter(
    (e) => e.programId !== entry.programId,
  );
  write(
    [
      {
        ...entry,
        // Preserve a previously-known programme name if this call has only the
        // raw id to offer -- the detail page knows the checklist, not always the
        // programme metadata.
        programName:
          entry.programName ||
          readChecklistIndex(userId).find((e) => e.programId === entry.programId)
            ?.programName ||
          entry.programId,
        lastOpenedAt: new Date().toISOString(),
      },
      ...existing,
    ],
    userId,
  );
}

export function forgetChecklist(programId: string, userId?: string | null): void {
  write(
    readChecklistIndex(userId).filter((e) => e.programId !== programId),
    userId,
  );
}

/** 0-100, or 0 for a checklist with no items. */
export function progressPercent(entry: ChecklistIndexEntry): number {
  if (entry.totalItems <= 0) return 0;
  return Math.round((entry.completedItems / entry.totalItems) * 100);
}

/** True when the stored name is the raw id or otherwise not human-readable. */
export function isPlaceholderProgramName(
  programName: string,
  programId: string,
): boolean {
  if (!programName.trim()) return true;
  if (programName === programId) return true;
  // UUID-style ids from some integrations.
  return /^[a-f0-9-]{20,}$/i.test(programName);
}

/** Secondary line under the programme title on checklist cards. */
export function checklistSubtitle(entry: ChecklistIndexEntry): string {
  const parts = [entry.university, entry.country].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "Programme checklist";
}

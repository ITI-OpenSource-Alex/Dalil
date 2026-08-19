// The checklist backend (GOA-084) persists no per-item duration ("estimatedDays"
// does not exist on ChecklistItem), so there is no real data to sum into an exact
// completion date. Rather than fabricate a precise-looking date from nothing, this
// applies one fixed, documented assumption and the UI labels the result
// "approximate" — see ChecklistProgress.tsx. Replace with real per-item durations
// once GOA-084's schema carries them.
export const ASSUMED_DAYS_PER_REMAINING_ITEM = 3;

export function estimateCompletionDate(
  remainingItemCount: number,
  today: Date = new Date(),
): Date | null {
  if (remainingItemCount <= 0) {
    return null;
  }
  const date = new Date(today);
  date.setDate(date.getDate() + remainingItemCount * ASSUMED_DAYS_PER_REMAINING_ITEM);
  return date;
}

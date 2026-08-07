/**
 * Collapses concurrent calls for the same GET into one network request.
 *
 * The Dashboard's widgets are deliberately independent (each owns its own
 * fetch, see components/dashboard/index.ts) so that adding one is a one-file
 * change, not a shared-data-layer change. The cost of that independence is
 * that two widgets needing the same data (e.g. WelcomeWidget and
 * ProgressWidget both call getMyProfile(); RecentActivityWidget and
 * PracticeShortcutsWidget both call listSpeakingSessions()/listEssays())
 * mount at the same time and each fire their own request for it, even
 * though the first response would have answered both.
 *
 * This closes that gap without touching widget independence or component
 * APIs: wrap a GET function's body in `dedupe(key, () => fetch(...))` and
 * any call that arrives while one is already in flight for the same key
 * gets the same promise instead of starting a second request. The entry is
 * removed as soon as it settles, so this only ever collapses genuinely
 * concurrent calls -- it is not a cache, and every call after the first has
 * resolved gets a fresh network request, same as before.
 */

const inFlight = new Map<string, Promise<unknown>>();

export function dedupe<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = inFlight.get(key);
  if (existing) return existing as Promise<T>;

  const promise = fn().finally(() => {
    inFlight.delete(key);
  });
  inFlight.set(key, promise);
  return promise;
}

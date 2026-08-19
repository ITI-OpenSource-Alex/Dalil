import { useCallback, useEffect, useState } from "react";
import { getMyProfile } from "@/lib/profile-api";
import type { CurrentUser, UserProfileDetail } from "@/app/types/profile";

export type FetchStatus = "idle" | "loading" | "success" | "error";

/** GOA-035/BUG-047: the authenticated user's real profile, replacing the hardcoded
 * CURRENT_USER_ID placeholder for the pages built on this ticket (profile, checklist).
 */
export function useCurrentUser() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      const data = await getMyProfile();
      setUser(data);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load your profile");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Optimistic patch for blur autosave; call `retry()` to roll back on failure. */
  const patchProfile = useCallback((partial: Partial<UserProfileDetail>) => {
    setUser((prev) => {
      if (!prev?.profile) return prev;
      return { ...prev, profile: { ...prev.profile, ...partial } };
    });
  }, []);

  return { user, status, error, retry: load, patchProfile };
}

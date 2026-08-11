"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ProfileNotReadyError,
  RateLimitedError,
  formatRetryAfter,
  searchOpportunities,
  type MatchedProgram,
} from "@/lib/opportunities-api";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";

export type MatchesStatus =
  | "loading"
  | "success"
  | "error"
  | "profile-incomplete"
  | "syncing"
  | "rate-limited";

const TOP_N = 10;

/**
 * Owns opportunity-match fetching for the profile hub.
 *
 * State lives here rather than in the matches panel because Radix unmounts an
 * inactive tab panel: a panel that fetched on mount would spend one of the
 * account's 20 hourly searches every time the user flicked back to the tab.
 *
 * A search happens only when the surface is visible AND the results on hand
 * are older than the last successful profile save (`savedAt`). Editing on
 * another tab therefore costs nothing until the user comes back to look.
 */
export function useOpportunityMatches({
  enabled,
  visible,
  savedAt,
}: {
  enabled: boolean;
  visible: boolean;
  savedAt: number;
}) {
  const upgrade = useUpgradePrompt();

  const [programs, setPrograms] = useState<MatchedProgram[]>([]);
  const [status, setStatus] = useState<MatchesStatus>(
    enabled ? "loading" : "profile-incomplete",
  );
  const [error, setError] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<string | null>(null);

  const inFlight = useRef(false);
  /** The `savedAt` the held results were ranked against; -1 means never. */
  const loadedFor = useRef(-1);

  const load = useCallback(
    async (forSave: number) => {
      // Also what makes React's development double-effect issue one request.
      if (inFlight.current) return;
      inFlight.current = true;
      setStatus("loading");
      setError(null);

      try {
        const results = await searchOpportunities();
        setPrograms(results.slice(0, TOP_N));
        setStatus("success");
      } catch (err) {
        if (err instanceof ProfileNotReadyError) {
          setStatus("syncing");
        } else if (err instanceof RateLimitedError) {
          setRetryAfter(formatRetryAfter(err.retryAfterSeconds));
          setStatus("rate-limited");
        } else if (upgrade.handle(err)) {
          setError(null);
          setStatus("error");
        } else {
          setError(
            "We couldn't reach programme matching just now. Your profile is unchanged — try again in a moment.",
          );
          setStatus("error");
        }
      } finally {
        inFlight.current = false;
        // Recorded on failure too: a failed search must not turn every tab
        // switch into an automatic retry. `reload` is the way back.
        loadedFor.current = forSave;
      }
    },
    [upgrade],
  );

  const reload = useCallback(() => {
    void load(savedAt);
  }, [load, savedAt]);

  useEffect(() => {
    if (!enabled) {
      setPrograms([]);
      setStatus("profile-incomplete");
      loadedFor.current = -1;
      return;
    }
    if (!visible) return;
    if (loadedFor.current === savedAt) return;
    void load(savedAt);
  }, [enabled, visible, savedAt, load]);

  return { programs, status, error, retryAfter, reload };
}

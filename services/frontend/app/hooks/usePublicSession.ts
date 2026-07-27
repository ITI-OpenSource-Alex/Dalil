import { useCallback, useEffect, useState } from "react";
import { getPublicSpeakingSession } from "@/lib/speaking-api";
import { SpeakingSessionDetail } from "@/app/types/speaking";
import { FetchStatus } from "./useSessionHistory";

/** Fetches a shared session by its public share token — no userId involved. */
export function usePublicSession(shareToken: string) {
  const [session, setSession] = useState<SpeakingSessionDetail | null>(null);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!shareToken) return;

    setStatus("loading");
    setError(null);

    try {
      const data = await getPublicSpeakingSession(shareToken);
      setSession(data);
      setStatus("success");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load shared session",
      );
      setStatus("error");
    }
  }, [shareToken]);

  useEffect(() => {
    load();
  }, [load]);

  return { session, status, error, retry: load };
}

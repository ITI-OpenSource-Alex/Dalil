import { useCallback, useEffect, useState } from "react";
import { getSpeakingSession } from "@/lib/speaking-api";
import { SpeakingSessionDetail } from "@/app/types/speaking";
import { FetchStatus } from "./useSessionHistory";

export function useSessionDetail(sessionId: string) {
  const [session, setSession] = useState<SpeakingSessionDetail | null>(null);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sessionId) return;

    setStatus("loading");
    setError(null);

    try {
      const data = await getSpeakingSession(sessionId);
      setSession(data);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session");
      setStatus("error");
    }
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  return { session, status, error, retry: load };
}

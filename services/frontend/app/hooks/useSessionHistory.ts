import { useCallback, useEffect, useState } from "react";
import { listSpeakingSessions } from "@/lib/speaking-api";
import { SpeakingSessionSummary } from "@/app/types/speaking";

export type FetchStatus = "idle" | "loading" | "success" | "error";

export function useSessionHistory() {
  const [sessions, setSessions] = useState<SpeakingSessionSummary[]>([]);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      const data = await listSpeakingSessions();
      setSessions(data);
      setStatus("success");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load session history",
      );
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { sessions, status, error, retry: load };
}

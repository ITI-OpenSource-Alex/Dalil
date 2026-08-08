import { useCallback, useEffect, useState } from "react";
import { listEssays } from "@/lib/writing-history-api";
import { EssayHistoryItem } from "@/app/types/writing";

export type FetchStatus = "idle" | "loading" | "success" | "error";

/** Mirrors useSessionHistory.ts's shape (Speaking) so the two history
 * screens share one mental model. */
export function useWritingHistory() {
  const [essays, setEssays] = useState<EssayHistoryItem[]>([]);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      const data = await listEssays();
      setEssays(data);
      setStatus("success");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load essay history",
      );
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { essays, status, error, retry: load };
}

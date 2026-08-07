import { useCallback, useEffect, useState } from "react";
import { getExamProgress, type ExamProgress } from "@/lib/exam-api";
import { isSubscriptionRequiredError } from "@/lib/subscription";

export type ExamProgressStatus =
  | "idle"
  | "loading"
  | "success"
  | "error"
  | "upgrade-required";

/**
 * GET /api/exam/progress, distinguishing a Free account's paywall 403 from a
 * real fault -- the Dashboard's IELTS summary widget needs to render an
 * upgrade nudge for the former and a generic empty state for the latter,
 * which a single "error" status can't express.
 */
export function useExamProgress() {
  const [progress, setProgress] = useState<ExamProgress>({});
  const [status, setStatus] = useState<ExamProgressStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      const data = await getExamProgress();
      setProgress(data);
      setStatus("success");
    } catch (err) {
      if (isSubscriptionRequiredError(err)) {
        setStatus("upgrade-required");
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load exam progress");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { progress, status, error, retry: load };
}

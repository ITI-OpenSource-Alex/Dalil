"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getExamHistory,
  getExamProgress,
  getWeakAreas,
  type ExamHistoryItem,
  type ExamProgress,
  type WeakAreas,
} from "@/lib/exam-api";
import { isExamProgressEmpty } from "@/lib/exam-progress";
import { isSubscriptionRequiredError } from "@/lib/subscription";

export type ResourceStatus =
  | "idle"
  | "loading"
  | "success"
  | "error"
  | "upgrade-required";

async function loadOne<T>(
  fn: () => Promise<T>,
): Promise<
  | { status: "success"; data: T }
  | { status: "error"; message: string }
  | { status: "upgrade-required" }
> {
  try {
    const data = await fn();
    return { status: "success", data };
  } catch (err) {
    if (isSubscriptionRequiredError(err)) {
      return { status: "upgrade-required" };
    }
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Request failed",
    };
  }
}

export function useExamProgressTab() {
  const [progress, setProgress] = useState<ExamProgress>({});
  const [history, setHistory] = useState<ExamHistoryItem[]>([]);
  const [weakAreas, setWeakAreas] = useState<WeakAreas>({});
  const [progressStatus, setProgressStatus] = useState<ResourceStatus>("idle");
  const [historyStatus, setHistoryStatus] = useState<ResourceStatus>("idle");
  const [weakAreasStatus, setWeakAreasStatus] =
    useState<ResourceStatus>("idle");
  const [progressError, setProgressError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [weakAreasError, setWeakAreasError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setProgressStatus("loading");
    setHistoryStatus("loading");
    setWeakAreasStatus("loading");
    setProgressError(null);
    setHistoryError(null);
    setWeakAreasError(null);

    const [p, h, w] = await Promise.all([
      loadOne(getExamProgress),
      loadOne(() => getExamHistory(1)),
      loadOne(getWeakAreas),
    ]);

    if (p.status === "success") {
      setProgress(p.data);
      setProgressStatus("success");
    } else if (p.status === "upgrade-required") {
      setProgressStatus("upgrade-required");
    } else {
      setProgressError(p.message);
      setProgressStatus("error");
    }

    if (h.status === "success") {
      setHistory(h.data);
      setHistoryStatus("success");
    } else if (h.status === "upgrade-required") {
      setHistoryStatus("upgrade-required");
    } else {
      setHistoryError(h.message);
      setHistoryStatus("error");
    }

    if (w.status === "success") {
      setWeakAreas(w.data);
      setWeakAreasStatus("success");
    } else if (w.status === "upgrade-required") {
      setWeakAreasStatus("upgrade-required");
    } else {
      setWeakAreasError(w.message);
      setWeakAreasStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const tab = useMemo(() => {
    const statuses = [progressStatus, historyStatus, weakAreasStatus];
    if (statuses.some((s) => s === "upgrade-required")) {
      return "upgrade-required" as const;
    }
    if (statuses.some((s) => s === "idle" || s === "loading")) {
      return "loading" as const;
    }
    if (progressStatus === "error" && historyStatus === "error") {
      return "hard-error" as const;
    }
    if (
      progressStatus === "success" &&
      historyStatus === "success" &&
      isExamProgressEmpty(progress, history.length)
    ) {
      return "empty" as const;
    }
    return "content" as const;
  }, [
    progressStatus,
    historyStatus,
    weakAreasStatus,
    progress,
    history.length,
  ]);

  return {
    progress,
    history,
    weakAreas,
    progressStatus,
    historyStatus,
    weakAreasStatus,
    progressError,
    historyError,
    weakAreasError,
    tab,
    retry: load,
  };
}

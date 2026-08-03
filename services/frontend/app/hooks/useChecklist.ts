import { useCallback, useEffect, useState } from "react";
import {
  getChecklist,
  getChecklistFinancials,
  updateChecklistItem,
} from "@/lib/checklist-api";
import type {
  ChecklistItem,
  ChecklistResponse,
  FinancialRequirementItem,
} from "@/app/types/checklist";

export type FetchStatus = "idle" | "loading" | "success" | "error";

export function useChecklist(programId: string) {
  const [checklist, setChecklist] = useState<ChecklistResponse | null>(null);
  const [financialItems, setFinancialItems] = useState<FinancialRequirementItem[]>([]);
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);

    try {
      // Two independent backends, fetched in parallel: the checklist itself
      // (GOA-084) and Financial Requirements (GOA-035, structured visa data only).
      // A country with no visa data yields an empty `items` array from the second
      // call rather than an error, so it never blocks the checklist from rendering.
      const [checklistResult, financialResult] = await Promise.all([
        getChecklist(programId),
        getChecklistFinancials(programId).catch(() => ({ items: [] })),
      ]);
      setChecklist(checklistResult);
      setFinancialItems(financialResult.items);
      setStatus("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load checklist");
      setStatus("error");
    }
  }, [programId]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleItem = useCallback(
    async (itemId: string, checked: boolean) => {
      if (!checklist) return;
      setToggleError(null);

      // Optimistic update, matching the pattern already used for exam answers:
      // flip locally first, roll back if the persist call fails.
      const previous = checklist;
      setChecklist({
        ...checklist,
        items: checklist.items.map((item: ChecklistItem) =>
          item.itemId === itemId ? { ...item, checked } : item,
        ),
      });

      try {
        await updateChecklistItem(programId, itemId, checked);
      } catch (err) {
        setChecklist(previous);
        setToggleError(
          err instanceof Error ? err.message : "Failed to save checklist item",
        );
      }
    },
    [checklist, programId],
  );

  return { checklist, financialItems, status, error, toggleError, retry: load, toggleItem };
}

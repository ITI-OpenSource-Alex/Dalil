import { useCallback, useEffect, useRef, useState } from "react";

export type ClipboardStatus = "idle" | "copied" | "error";

/**
 * Thin wrapper around navigator.clipboard.writeText with a timed "copied"
 * status. Callers are responsible for offering a manual-select fallback
 * when copy() resolves false (clipboard API unavailable/denied/non-secure
 * context) — this hook only reports success/failure, it doesn't render UI.
 */
export function useClipboard(resetDelayMs = 2000) {
  const [status, setStatus] = useState<ClipboardStatus>("idle");
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);

      const canUseClipboardAPI =
        typeof navigator !== "undefined" &&
        !!navigator.clipboard &&
        window.isSecureContext;

      try {
        if (!canUseClipboardAPI) {
          throw new Error("Clipboard API unavailable in this context");
        }
        await navigator.clipboard.writeText(text);
        setStatus("copied");
        timeoutRef.current = setTimeout(() => setStatus("idle"), resetDelayMs);
        return true;
      } catch (err) {
        console.error("useClipboard: failed to copy text", err);
        setStatus("error");
        timeoutRef.current = setTimeout(() => setStatus("idle"), resetDelayMs);
        return false;
      }
    },
    [resetDelayMs],
  );

  return { status, copy };
}

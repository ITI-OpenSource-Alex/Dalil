"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  READING_SPLIT_DEFAULT,
  READING_SPLIT_MAX,
  READING_SPLIT_MIN,
  READING_SPLIT_STEP,
  clampReadingSplitPercent,
  loadReadingSplitPercent,
  percentFromClientX,
  saveReadingSplitPercent,
} from "@/lib/reading-split";

/**
 * Resizable passage | questions split for the Reading exam.
 * Persists the passage width percent in localStorage.
 */
export function useReadingSplit() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [passagePercent, setPassagePercent] = useState(READING_SPLIT_DEFAULT);
  const draggingRef = useRef(false);

  useEffect(() => {
    setPassagePercent(loadReadingSplitPercent());
  }, []);

  const commit = useCallback((next: number) => {
    const clamped = clampReadingSplitPercent(next);
    setPassagePercent(clamped);
    saveReadingSplitPercent(clamped);
  }, []);

  const updateFromClientX = useCallback(
    (clientX: number) => {
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      commit(percentFromClientX(clientX, rect.left, rect.width));
    },
    [commit],
  );

  const onSeparatorPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      draggingRef.current = true;
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      updateFromClientX(event.clientX);

      const onMove = (e: PointerEvent) => {
        if (!draggingRef.current) return;
        updateFromClientX(e.clientX);
      };
      const onUp = (e: PointerEvent) => {
        draggingRef.current = false;
        try {
          target.releasePointerCapture(e.pointerId);
        } catch {
          // already released
        }
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [updateFromClientX],
  );

  const onSeparatorKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        commit(passagePercent - READING_SPLIT_STEP);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        commit(passagePercent + READING_SPLIT_STEP);
      } else if (event.key === "Home") {
        event.preventDefault();
        commit(READING_SPLIT_MIN);
      } else if (event.key === "End") {
        event.preventDefault();
        commit(READING_SPLIT_MAX);
      }
    },
    [commit, passagePercent],
  );

  return {
    containerRef,
    passagePercent,
    onSeparatorPointerDown,
    onSeparatorKeyDown,
    min: READING_SPLIT_MIN,
    max: READING_SPLIT_MAX,
  };
}

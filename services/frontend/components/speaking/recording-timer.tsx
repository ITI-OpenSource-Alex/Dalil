"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import type { SpeakingState } from "@/components/speaking/speaking-status";

interface RecordingTimerProps {
  state: SpeakingState;
  /**
   * Bumped by the caller whenever a new speaking session begins (including
   * retrying from an open panel, e.g. via "Try again" after an error) — the
   * one explicit signal that resets the clock, independent of whether the
   * panel itself ever unmounted.
   */
  sessionKey: number;
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/**
 * Elapsed-time pill for the current (or just-finished) take.
 *
 * Deliberately its own leaf component: it ticks on a local interval, so a
 * running clock only re-renders this small pill, not the rest of the
 * speaking panel. `aria-hidden` for the same reason StatusChip is — a
 * once-a-second announcement would be noise; the panel's single
 * `role="status"` region already covers state changes.
 */
export default function RecordingTimer({ state, sessionKey }: RecordingTimerProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const prevSessionKeyRef = useRef(sessionKey);

  const isRecording = state === "listening";
  const isProcessing = state === "transcribing" || state === "evaluating";
  const isDone = state === "done";

  // New session -> back to zero, regardless of what the elapsed value was.
  useEffect(() => {
    if (prevSessionKeyRef.current !== sessionKey) {
      prevSessionKeyRef.current = sessionKey;
      setElapsedSeconds(0);
    }
  }, [sessionKey]);

  useEffect(() => {
    if (!isRecording) return;

    // Anchored to a wall-clock timestamp rather than counting ticks, so a
    // throttled/backgrounded tab can't make the displayed value drift from
    // real elapsed time.
    const startedAt = Date.now() - elapsedSeconds * 1000;
    const id = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);

    return () => clearInterval(id);
    // elapsedSeconds is read once, only to anchor startedAt at the instant
    // recording begins (always 0 then, via the reset effect above) — not to
    // restart the interval on every tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording]);

  if (!isRecording && !isProcessing && !isDone) return null;

  const label = isRecording ? "Recording" : isProcessing ? "Processing" : "Duration";

  return (
    <motion.div
      aria-hidden="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="absolute top-3 right-3 z-20 flex items-center gap-1.5 rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-medium text-[#0D3820] shadow-sm ring-1 ring-black/5 backdrop-blur-sm"
    >
      {isRecording && (
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-rose-500" />
      )}
      <span>
        {label} <span className="tabular-nums">• {formatDuration(elapsedSeconds)}</span>
      </span>
    </motion.div>
  );
}

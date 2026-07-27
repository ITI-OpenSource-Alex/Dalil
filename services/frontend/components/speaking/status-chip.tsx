"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Loader2 } from "lucide-react";
import {
  SPEAKING_STATE_META,
  type SpeakingState,
} from "@/components/speaking/speaking-status";

interface StatusChipProps {
  state: SpeakingState;
}

/**
 * Compact state badge for the speaking panel header.
 *
 * Marked aria-hidden on purpose: the panel owns a single visually-hidden
 * live region that announces status changes, so exposing the chip too would
 * make screen readers read every transition twice.
 */
export default function StatusChip({ state }: StatusChipProps) {
  const meta = SPEAKING_STATE_META[state];
  const reduceMotion = useReducedMotion();

  return (
    <motion.span
      aria-hidden="true"
      layout
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${meta.bg} ${meta.border} ${meta.text}`}
    >
      {meta.busy ? (
        <Loader2
          size={12}
          className={reduceMotion ? "" : "animate-spin"}
          strokeWidth={2.5}
        />
      ) : (
        <span className="relative flex h-2 w-2">
          {/* Live "breathing" halo only while actively listening. */}
          {state === "listening" && !reduceMotion && (
            <span
              className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-70 ${meta.accent}`}
            />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${meta.accent}`}
          />
        </span>
      )}
      {meta.label}
    </motion.span>
  );
}

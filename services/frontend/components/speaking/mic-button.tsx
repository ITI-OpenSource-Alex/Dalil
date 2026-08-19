"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Check, Loader2, Mic, Square } from "lucide-react";
import {
  isStartState,
  type SpeakingState,
} from "@/components/speaking/speaking-status";

interface MicButtonProps {
  state: SpeakingState;
  onStart: () => void;
  onStop: () => void;
  /**
   * Set while another practice mode (Writing) owns the session, so a new
   * recording can't be started out from under it. Only ever applies to the
   * "start" action — an already-running recording is never interrupted by
   * this (see the session-lock derivation in chat-shell.tsx: a genuine
   * recording implies Speaking already owns the session, so this can't be
   * true at the same time).
   */
  disabledReason?: string;
  canBargeIn?: boolean;
  onBargeIn?: () => void;
}

/**
 * Circular voice control, in the vein of ChatGPT Voice / Voice Memos.
 *
 * Which callback fires for which state is unchanged from the previous
 * implementation — `isStartState` encodes exactly the original condition. Only
 * the visual treatment per state is new.
 */
export default function MicButton({
  state,
  onStart,
  onStop,
  disabledReason,
  canBargeIn = false,
  onBargeIn,
}: MicButtonProps) {
  const reduceMotion = useReducedMotion();
  const isStart = isStartState(state);
  const isConnecting = state === "connecting";
  const isListening = state === "listening";
  const isProcessing =
    state === "transcribing" ||
    state === "evaluating" ||
    state === "examiner" ||
    state === "preparing";
  const isDone = state === "done";
  const isBargeIn = state === "examiner" && canBargeIn;
  const isLocked = isStart && !isConnecting && Boolean(disabledReason);

  // Surface treatment per state. Rose while capturing (the universal
  // "recording" affordance), emerald at rest, neutral while the system is
  // busy so it doesn't compete with the status chip for attention.
  const surface = isListening
    ? "bg-rose-600 hover:bg-rose-700 focus-visible:ring-rose-500/40"
    : isProcessing
      ? "bg-[#8C9A8E] focus-visible:ring-[#8C9A8E]/40"
      : isDone
        ? "bg-emerald-600 hover:bg-emerald-700 focus-visible:ring-emerald-500/40"
        : "bg-emerald-700 hover:bg-emerald-800 focus-visible:ring-emerald-600/40";

  const label = isBargeIn
    ? "Interrupt examiner and answer"
    : isStart
    ? isConnecting
      ? "Connecting to speaking session"
      : isLocked
        ? `Start speaking (unavailable: ${disabledReason})`
        : "Start speaking"
    : isListening
      ? "Stop recording"
      : "End speaking session";

  const icon = isBargeIn ? (
    <Mic size={26} />
  ) : isConnecting || isProcessing ? (
    <Loader2 size={26} className={reduceMotion ? "" : "animate-spin"} />
  ) : isListening ? (
    <Square size={22} fill="currentColor" />
  ) : isDone ? (
    <Check size={26} strokeWidth={2.5} />
  ) : (
    <Mic size={26} />
  );

  return (
    <div className="relative flex h-20 w-20 items-center justify-center">
      {/* Expanding halo rings: a continuous, non-blocking signal that the mic
          is genuinely open. Suppressed under reduced-motion. */}
      {isListening && !reduceMotion && (
        <>
          <motion.span
            aria-hidden="true"
            className="absolute inset-0 rounded-full bg-rose-500/25"
            animate={{ scale: [1, 1.45], opacity: [0.5, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
          />
          <motion.span
            aria-hidden="true"
            className="absolute inset-0 rounded-full bg-rose-500/25"
            animate={{ scale: [1, 1.45], opacity: [0.5, 0] }}
            transition={{
              duration: 1.8,
              repeat: Infinity,
              ease: "easeOut",
              delay: 0.9,
            }}
          />
        </>
      )}

      <motion.button
        data-testid={isBargeIn ? "barge-in-button" : isStart ? "start-speaking-button" : "stop-speaking-button"}
        onClick={isBargeIn ? onBargeIn : isStart ? onStart : onStop}
        disabled={isConnecting || isLocked || (isProcessing && !isBargeIn)}
        aria-label={label}
        aria-busy={isConnecting || isProcessing}
        title={isLocked ? disabledReason : undefined}
        whileHover={
          reduceMotion || isConnecting || isLocked ? undefined : { scale: 1.04 }
        }
        whileTap={
          reduceMotion || isConnecting || isLocked ? undefined : { scale: 0.96 }
        }
        transition={{ type: "spring", stiffness: 400, damping: 25 }}
        className={`relative flex h-16 w-16 items-center justify-center rounded-full text-white shadow-lg shadow-black/10 outline-none transition-colors focus-visible:ring-4 disabled:cursor-not-allowed disabled:opacity-70 ${surface}`}
      >
        {icon}
      </motion.button>
    </div>
  );
}

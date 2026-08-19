"use client";

import { useState, useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AudioLines, MessageSquareText, X } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import WaveformCanvas from "@/components/speaking/waveform-canvas";
import StatusChip from "@/components/speaking/status-chip";
import MicButton from "@/components/speaking/mic-button";
import InlineAlert from "@/components/speaking/inline-alert";
import RecordingTimer from "@/components/speaking/recording-timer";
import {
  SPEAKING_STATE_META,
  isStartState,
  speakingHint,
  type SpeakingState,
} from "@/components/speaking/speaking-status";
import type { SpeakingCueCard } from "@/lib/speaking-websocket";

// Re-exported so existing importers (chat-shell.tsx) keep working unchanged.
export type { SpeakingState };

interface SpeakingSessionPanelProps {
  open: boolean;
  transcript: string;
  state: SpeakingState;
  error?: string | null;
  /** The live microphone stream once recording has actually started. */
  audioStream?: MediaStream | null;
  /**
   * Increments whenever a new speaking session begins. Drives the recording
   * timer's reset — see recording-timer.tsx for why this can't just be
   * derived from mount/unmount.
   */
  sessionKey: number;
  /**
   * Set while Writing Practice owns the session, so Speaking can't be
   * started out from under it. Disables the Start action and surfaces the
   * reason as both a tooltip and inline helper text.
   */
  disabledReason?: string;
  part?: 1 | 2 | 3;
  partLabel?: string;
  examinerText?: string;
  cueCard?: SpeakingCueCard | null;
  remainingSeconds?: number | null;
  onStart: () => void;
  onStop: () => void;
  onClose: () => void;
  canBargeIn?: boolean;
  onBargeIn?: () => void;
  title?: string;
}

/** Static bars shown when the visualiser is idle, so the stage never collapses. */
const RESTING_BAR_HEIGHTS = [
  10, 16, 24, 14, 30, 20, 36, 22, 44, 26, 34, 18, 28, 14, 22, 12, 18, 10,
];

export default function SpeakingSessionPanel({
  open,
  transcript,
  state,
  error,
  audioStream = null,
  sessionKey,
  disabledReason,
  part = 1,
  partLabel = "Introduction and interview",
  examinerText,
  cueCard,
  remainingSeconds,
  onStart,
  onStop,
  onClose,
  canBargeIn = false,
  onBargeIn,
  title = "Speaking Practice",
}: SpeakingSessionPanelProps) {
  const reduceMotion = useReducedMotion();
  const [showExaminerTranscript, setShowExaminerTranscript] = useState<boolean>(true);

  useEffect(() => {
    const saved = localStorage.getItem("dalil:speaking:show-examiner-transcript");
    if (saved !== null) {
      setShowExaminerTranscript(saved === "true");
    }
  }, []);

  const handleToggleTranscript = (checked: boolean) => {
    setShowExaminerTranscript(checked);
    localStorage.setItem("dalil:speaking:show-examiner-transcript", String(checked));
  };

  if (!open) return null;

  const meta = SPEAKING_STATE_META[state];
  const isRecording = state === "listening";
  const canRetry = isStartState(state) && state !== "connecting";
  const isLocked = canRetry && Boolean(disabledReason);

  return (
    <motion.div
      data-testid="speaking-panel"
      initial={reduceMotion ? false : { opacity: 0, y: 12, scale: 0.99 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className="mb-6 overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_1px_2px_rgba(13,56,32,0.04),0_8px_24px_-12px_rgba(13,56,32,0.15)]"
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span
            aria-hidden="true"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-muted text-brand-fg"
          >
            <AudioLines size={18} />
          </span>

          <div className="min-w-0">
            {/* Deliberately not truncated: the chat column can get very narrow,
                and wrapping to two lines reads far better than "Spe…". */}
            <h3 className="text-sm leading-snug font-semibold text-balance text-brand-fg">
              {title}
            </h3>

            {/*
              The single canonical status announcement. Visually hidden because
              the chip already communicates state to sighted users; exposing
              both would double-announce every transition.
            */}
            <span className="sr-only" role="status" aria-live="polite">
              Status: {meta.label}
            </span>

            {/* Secondary detail is the first thing to go when space is tight. */}
            <p className="hidden truncate text-xs text-fg-subtle sm:block">
              Full IELTS Speaking interview
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden sm:block">
            <StatusChip state={state} />
          </span>

          <button
            data-testid="close-speaking-button"
            onClick={onClose}
            aria-label={`Close ${title.toLowerCase()}`}
            className="rounded-lg p-2 text-fg-subtle outline-none transition-colors hover:bg-canvas-subtle hover:text-brand-fg focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────── */}
      <div className="space-y-6 px-4 py-6 sm:px-6">
        {/* Status chip moves inline below the header on narrow screens. */}
        <div className="sm:hidden">
          <StatusChip state={state} />
        </div>

        <section aria-label="Interview progress" className="space-y-3">
          <div
            className="flex items-center gap-2"
            data-testid="speaking-part-indicator"
          >
            {[1, 2, 3].map((number) => (
              <span
                key={number}
                className={`flex h-7 min-w-7 items-center justify-center rounded-full border px-2 text-xs font-semibold ${
                  number === part
                    ? "border-emerald-700 bg-emerald-700 text-white"
                    : number < part
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : "border-border bg-canvas-subtle text-fg-subtle"
                }`}
              >
                {number}
              </span>
            ))}
            <span className="ml-1 text-sm font-medium text-brand-fg">
              {partLabel}
            </span>
            {remainingSeconds !== null && remainingSeconds !== undefined && (
              <span
                data-testid="speaking-countdown"
                className="ml-auto rounded-full bg-amber-50 px-3 py-1 text-sm font-semibold tabular-nums text-amber-800"
              >
                {Math.max(0, remainingSeconds)}s
              </span>
            )}
          </div>

          {examinerText && (
            <div
              data-testid="examiner-turn"
              className="rounded-xl border border-violet-100 bg-violet-50/70 p-4 transition-all"
            >
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold tracking-wide text-violet-700 uppercase">
                  Examiner
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-violet-900">
                    Subtitles
                  </span>
                  <Switch
                    checked={showExaminerTranscript}
                    onChange={handleToggleTranscript}
                    aria-label="Toggle Examiner Subtitles"
                  />
                </div>
              </div>
              {showExaminerTranscript ? (
                <p className="text-sm leading-relaxed text-violet-950">
                  {examinerText}
                </p>
              ) : (
                <p className="text-xs italic text-violet-600/80">
                  Examiner subtitles turned off.
                </p>
              )}
            </div>
          )}

          {cueCard && (
            <div
              data-testid="speaking-cue-card"
              className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950"
            >
              <p className="text-base font-semibold">{cueCard.topic}</p>
              <p className="mt-3 text-xs font-semibold tracking-wide uppercase">
                You should say
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {cueCard.prompts.map((prompt) => (
                  <li key={prompt}>{prompt}</li>
                ))}
              </ul>
              <p className="mt-3 text-sm">{cueCard.closing_prompt}</p>
            </div>
          )}
        </section>

        {/* Waveform stage — the visual anchor of the whole panel. */}
        <div className="relative h-28 overflow-hidden rounded-2xl bg-linear-to-b from-canvas-subtle to-canvas-inset ring-1 ring-inset ring-border sm:h-36">
          {/* Soft vignette so bars fade at the edges rather than being clipped. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(to_right,var(--color-canvas-subtle)_0%,transparent_8%,transparent_92%,var(--color-canvas-inset)_100%)]"
          />

          <RecordingTimer state={state} sessionKey={sessionKey} />

          <AnimatePresence mode="wait" initial={false}>
            {isRecording ? (
              <motion.div
                key="live"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.28, ease: "easeOut" }}
                className="absolute inset-0 px-4 py-4"
              >
                <WaveformCanvas stream={audioStream} active={isRecording} />
              </motion.div>
            ) : (
              <motion.div
                key="resting"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.28, ease: "easeOut" }}
                className="absolute inset-0 flex items-center justify-center gap-1 px-4"
                aria-hidden="true"
              >
                {RESTING_BAR_HEIGHTS.map((h, i) => (
                  <motion.span
                    key={i}
                    className="w-1 rounded-full bg-border-strong"
                    style={{ height: h }}
                    animate={
                      reduceMotion ? undefined : { opacity: [0.45, 0.85, 0.45] }
                    }
                    transition={{
                      duration: 2.4,
                      repeat: Infinity,
                      ease: "easeInOut",
                      delay: i * 0.06,
                    }}
                  />
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Error surface */}
        <AnimatePresence initial={false}>
          {error && (
            <InlineAlert
              key="speaking-error"
              title="Speaking session problem"
              description={error}
              onRetry={canRetry ? onStart : undefined}
            />
          )}
        </AnimatePresence>

        {/* Transcript */}
        <div className="rounded-2xl border border-border bg-canvas-subtle p-4">
          <div className="mb-2 flex items-center gap-2">
            <MessageSquareText
              size={14}
              className="text-fg-subtle"
              aria-hidden="true"
            />
            <span className="text-[11px] font-medium tracking-wide text-fg-subtle uppercase">
              Transcript
            </span>
          </div>

          <div
            data-testid="live-transcript"
            className="max-h-32 overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap text-fg"
          >
            {transcript ? (
              // Keyed so each update fades in rather than snapping.
              <motion.span
                key={transcript}
                initial={reduceMotion ? false : { opacity: 0, y: 2 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
                className="block"
              >
                {transcript}
              </motion.span>
            ) : (
              <span className="text-fg-subtle italic">
                Your words will appear here as you speak.
              </span>
            )}
          </div>
        </div>

        {/* Primary control */}
        <div className="flex flex-col items-center gap-3 pt-1">
          <MicButton
            state={state}
            onStart={onStart}
            onStop={onStop}
            disabledReason={disabledReason}
            canBargeIn={canBargeIn}
            onBargeIn={onBargeIn}
          />

          <AnimatePresence mode="wait" initial={false}>
            <motion.p
              key={isLocked ? `locked-${state}` : state}
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              className={`text-xs ${isLocked ? "text-warning-fg" : "text-fg-subtle"}`}
            >
              {isLocked ? disabledReason : speakingHint(state)}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}

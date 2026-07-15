"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, X } from "lucide-react";

export type SpeakingState =
  | "idle"
  | "listening"
  | "transcribing"
  | "evaluating"
  | "done"
  | "error";

interface SpeakingSessionPanelProps {
  open: boolean;
  transcript: string;
  state: SpeakingState;
  error?: string | null;
  onStart: () => void;
  onStop: () => void;
  onClose: () => void;
}

export default function SpeakingSessionPanel({
  open,
  transcript,
  state,
  error,
  onStart,
  onStop,
  onClose,
}: SpeakingSessionPanelProps) {
  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        data-testid="speaking-panel"
        initial={{
          opacity: 0,
          y: 16,
        }}
        animate={{
          opacity: 1,
          y: 0,
        }}
        exit={{
          opacity: 0,
          y: 16,
        }}
        className="
          mb-4
          rounded-xl
          border
          border-emerald-100
          bg-white
          p-4
          shadow-sm
        "
      >
        <div
          className="
            mb-4
            flex
            items-center
            justify-between
          "
        >
          <div>
            <h3
              className="
                font-semibold
                text-[#0D3820]
              "
            >
              Speaking Practice
            </h3>

            <p
              className="
                text-xs
                text-[#526053]
                capitalize
              "
            >
              Status: {state}
            </p>
          </div>

          <button
            data-testid="close-speaking-button"
            onClick={onClose}
            className="
              rounded-lg
              p-2
              hover:bg-gray-100
            "
          >
            <X size={18} />
          </button>
        </div>

        {error && (
          <div
            className="
              mb-3
              rounded-lg
              bg-red-50
              p-3
              text-sm
              text-red-700
            "
          >
            {error}
          </div>
        )}

        <div
          className="
            min-h-22.5
            rounded-lg
            border
            bg-[#FAFBF9]
            p-3
          "
        >
          <p
            data-testid="live-transcript"
            className="
              whitespace-pre-wrap
              text-sm
            "
          >
            {transcript || "Transcript will appear here..."}
          </p>
        </div>

        <div
          className="
            mt-4
            flex
            items-center
            gap-3
          "
        >
          {state === "idle" || state === "error" ? (
            <button
              data-testid="start-speaking-button"
              onClick={onStart}
              className="
                flex
                items-center
                gap-2
                rounded-lg
                bg-emerald-700
                px-4
                py-2
                text-white
                hover:bg-emerald-800
              "
            >
              <Mic size={18} />
              Start Speaking
            </button>
          ) : (
            <button
              data-testid="stop-speaking-button"
              onClick={onStop}
              className="
                flex
                items-center
                gap-2
                rounded-lg
                bg-red-600
                px-4
                py-2
                text-white
                hover:bg-red-700
              "
            >
              <MicOff size={18} />
              Stop
            </button>
          )}

          <div
            className="
              flex
              items-center
              gap-2
            "
          >
            <span
              className="
                h-3
                w-3
                animate-pulse
                rounded-full
                bg-red-500
              "
            />

            <span
              className="
                text-xs
                text-[#526053]
              "
            >
              {state}
            </span>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

"use client";

import { motion } from "framer-motion";
import { AlertCircle, RotateCcw } from "lucide-react";

interface InlineAlertProps {
  title: string;
  description: string;
  /** Renders a retry affordance when provided. */
  onRetry?: () => void;
  retryLabel?: string;
}

/**
 * Inline error surface: icon + title + description, with an optional recovery
 * action. Announced assertively because it always follows a user action that
 * has just failed.
 */
export default function InlineAlert({
  title,
  description,
  onRetry,
  retryLabel = "Try again",
}: InlineAlertProps) {
  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-start gap-3 rounded-xl border border-red-200/80 bg-red-50/80 p-4"
    >
      <AlertCircle
        size={18}
        className="mt-0.5 shrink-0 text-red-600"
        aria-hidden="true"
      />

      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-red-900">{title}</p>
        <p className="mt-1 text-xs leading-relaxed text-red-700">
          {description}
        </p>

        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 outline-none transition-colors hover:bg-red-50 focus-visible:ring-2 focus-visible:ring-red-500/40"
          >
            <RotateCcw size={13} aria-hidden="true" />
            {retryLabel}
          </button>
        )}
      </div>
    </motion.div>
  );
}

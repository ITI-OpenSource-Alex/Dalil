"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { PenSquare } from "lucide-react";

interface EssayComposerProps {
  loading?: boolean;
  onSubmit: (essay: string) => void;
  onCancel?: () => void;
}

export default function EssayComposer({
  loading = false,
  onSubmit,
  onCancel,
}: EssayComposerProps) {
  const [essay, setEssay] = useState("");

  const submitEssay = () => {
    if (!essay.trim()) return;

    onSubmit(essay);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-surface shadow-sm p-5 space-y-4"
    >
      <div className="flex items-center gap-2">
        <PenSquare size={18} className="text-brand-fg" aria-hidden="true" />

        <div>
          <h3 className="font-semibold text-brand-fg">
            IELTS Writing Practice
          </h3>

          <p className="text-xs text-fg-muted">
            Paste or write your essay below.
          </p>
        </div>
      </div>

      <textarea
        data-testid="essay-input"
        value={essay}
        onChange={(e) => setEssay(e.target.value)}
        rows={10}
        placeholder="Write your IELTS essay here..."
        className="w-full resize-y rounded-lg border border-border bg-surface p-4 text-sm outline-none focus:ring-2 focus:ring-brand-muted"
      />

      <div className="flex justify-between items-center">
        <span className="text-xs text-fg-muted">
          {essay.length} characters
        </span>

        <div className="flex gap-3">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 rounded-lg border border-border hover:bg-canvas-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
            >
              Cancel
            </button>
          )}

          <button
            data-testid="submit-essay-button"
            type="button"
            disabled={loading || essay.trim().length === 0}
            onClick={submitEssay}
            className="rounded-lg bg-brand px-5 py-2 text-fg-on-brand disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            {loading ? "Submitting..." : "Evaluate Essay"}
          </button>
        </div>
      </div>
    </motion.div>
  );
}

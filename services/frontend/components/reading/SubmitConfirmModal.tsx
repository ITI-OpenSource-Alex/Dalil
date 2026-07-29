"use client";

interface Props {
  unansweredCount: number;
  submitting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Reading-specific submit confirmation. Deliberately not a reuse of the
 * exam shell's existing modal (app/exam/shell/page.tsx) — that modal has a
 * static message and its confirm action is hardcoded to Writing's
 * {task1, task2} payload shape, with no concept of "unanswered questions".
 * Generalizing it to cover both would mean touching an already-shipped
 * Writing code path for the sake of one shared shell, which is outside
 * GOA-055's scope.
 */
export default function SubmitConfirmModal({
  unansweredCount,
  submitting,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="reading-submit-modal-title"
      className="fixed inset-0 z-150 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs"
    >
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-xl">
        <h3
          id="reading-submit-modal-title"
          className="mb-1 text-base font-bold text-gray-900"
        >
          Submit Reading exam?
        </h3>

        {unansweredCount > 0 ? (
          <p
            data-testid="unanswered-count-warning"
            className="mb-6 text-xs text-amber-700"
          >
            You have <strong>{unansweredCount}</strong> unanswered question
            {unansweredCount === 1 ? "" : "s"}. Once submitted, you can&apos;t
            go back and change your answers.
          </p>
        ) : (
          <p className="mb-6 text-xs text-gray-500">
            All 40 questions are answered. Ready to submit.
          </p>
        )}

        <div className="flex justify-end gap-2 text-xs font-semibold">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="rounded-full border border-gray-200 px-4 py-2 text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="confirm-submit-button"
            onClick={onConfirm}
            disabled={submitting}
            className="rounded-full bg-[#0d4d3a] px-4 py-2 text-white transition hover:bg-[#09382a] disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit & Exit"}
          </button>
        </div>
      </div>
    </div>
  );
}

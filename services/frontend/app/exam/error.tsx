"use client";

// Narrower error boundary scoped to /exam and its children
// (/exam/shell, /exam/results). Catches an exam-specific crash before it
// falls through to the root boundary (app/error.tsx) -- doc 10. Same
// constraints as the root boundary: no data fetching, no logic that could
// itself throw, and a plain <a> rather than next/link.
export default function ExamError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#fbfbfa] p-6">
      <div className="w-full max-w-sm rounded-2xl border border-gray-200/80 bg-white p-8 text-center shadow-2xs">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-2xl">
          ⚠️
        </div>

        <h1 className="mt-4 text-lg font-serif font-bold text-gray-900">
          Something went wrong with this exam
        </h1>

        <p className="mt-2 text-sm text-gray-500">
          An unexpected error interrupted this screen. Your progress up to
          the last save is safe on the server.
        </p>

        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#09382a]"
          >
            Try again
          </button>

          <a
            href="/exam"
            className="rounded-full border border-gray-200 px-4 py-2 text-xs font-semibold text-gray-700 transition hover:bg-gray-50"
          >
            Back to Skills Workspace
          </a>
        </div>
      </div>
    </div>
  );
}

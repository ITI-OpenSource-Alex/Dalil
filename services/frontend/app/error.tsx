"use client";

// Next.js App Router error boundary convention. Catches any unhandled
// render-time throw anywhere in the tree that isn't caught by a more
// specific boundary (e.g. app/exam/error.tsx) and shows a recoverable,
// on-brand state instead of a white screen -- the single highest
// insurance-value item in the demo-readiness plan (doc 10).
//
// This component must never itself be capable of throwing: no data
// fetching, no dependency on app state that might be undefined in a
// crashed tree. A plain <a> is used instead of next/link deliberately --
// the root boundary replaces the entire tree including the root layout
// when triggered, so it shouldn't lean on any app router context that may
// itself be part of what's broken.
//
// The ROOT app/error.tsx specifically replaces the root layout entirely
// when active, so — per the Next.js App Router convention — it must
// render its own <html>/<body> rather than relying on app/layout.tsx's.
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#fbfbfa] font-sans antialiased">
        <div className="flex min-h-screen items-center justify-center p-6">
          <div className="w-full max-w-sm rounded-2xl border border-gray-200/80 bg-white p-8 text-center shadow-2xs">
            <div
              className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-2xl"
              aria-hidden="true"
            >
              ⚠️
            </div>

            <h1 className="mt-4 text-lg font-serif font-bold text-gray-900">
              Something went wrong
            </h1>

            <p className="mt-2 text-sm text-gray-500">
              An unexpected error interrupted this page. You can try again,
              or head back to a safe screen.
            </p>

            <div className="mt-6 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => reset()}
                className="rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#09382a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                Try again
              </button>

              <a
                href="/chat"
                className="rounded-full border border-gray-200 px-4 py-2 text-xs font-semibold text-gray-700 transition hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                Back to Chat
              </a>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}

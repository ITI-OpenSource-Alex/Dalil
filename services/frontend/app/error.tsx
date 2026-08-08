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
// the router context may itself be part of what is broken.
//
// It renders NO <html>/<body> of its own. That is the distinction between
// the two App Router error conventions, and getting it wrong is worse than
// having no boundary at all:
//
//   app/error.tsx        renders *inside* the root layout, which stays
//                        mounted. It must emit ordinary content.
//   app/global-error.tsx replaces the root layout, and is the only one
//                        that owns <html>/<body>.
//
// This file previously did the latter while being the former, so the
// recovery UI mounted a second <html> inside app/layout.tsx's <body>.
// React refuses that ("You are mounting a new html component when a
// previous one has not first unmounted"), the boundary fails to hydrate,
// and "Try again" cannot recover -- so any incidental error, however
// transient, became a permanent dead end reading "Something went wrong".
export default function RootError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface p-8 text-center shadow-e2">
        <div
          className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-danger-subtle text-2xl"
          aria-hidden="true"
        >
          ⚠️
        </div>

        <h1 className="mt-4 font-serif text-lg font-bold text-fg">
          Something went wrong
        </h1>

        <p className="mt-2 text-sm text-fg-muted">
          An unexpected error interrupted this page. You can try again, or head
          back to a safe screen.
        </p>

        <div className="mt-6 flex flex-col gap-2">
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-full bg-brand px-4 py-2 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            Try again
          </button>

          <a
            href="/chat"
            className="rounded-full border border-border px-4 py-2 text-xs font-semibold text-fg-muted transition hover:bg-canvas-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            Back to Chat
          </a>
        </div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { Sidebar } from "@/components/ui/sidebar";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import SessionHistoryList from "@/components/speaking/session-history-list";
import BandTrendChart from "@/components/speaking/band-trend-chart";
import { CURRENT_USER_ID } from "@/lib/current-user";

export default function SpeakingHistoryPage() {
  const {
    user,
    status: profileStatus,
    error: profileError,
    retry: retryProfile,
  } = useCurrentUser();
  const userId = user?.id ?? CURRENT_USER_ID;
  const {
    sessions,
    status: historyStatus,
    error: historyError,
    retry: retryHistory,
  } = useSessionHistory(userId);

  // GOA-035/BUG-047: reuse the existing skeleton for the identity fetch too,
  // rather than adding a second loading treatment -- and surface the real
  // profile error (with its own retry) instead of silently falling through
  // to the CURRENT_USER_ID fallback's (wrong) session history.
  const identityLoading =
    profileStatus === "loading" || profileStatus === "idle";
  const status = identityLoading
    ? "loading"
    : profileStatus === "error"
      ? "error"
      : historyStatus;
  const error = profileStatus === "error" ? profileError : historyError;
  const retry = profileStatus === "error" ? retryProfile : retryHistory;

  return (
    <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <Sidebar />

      <main className="flex-1 p-8 md:p-12 max-w-4xl mx-auto">
        <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
              Speaking Practice
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-serif text-gray-900">
              Session History
            </h2>
          </div>
          <Link
            href="/chat"
            className="inline-block shrink-0 rounded-full bg-[#0d4d3a] px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-[#09382a]"
          >
            Practice Again
          </Link>
        </div>

        {status === "loading" && <HistoryLoadingSkeleton />}

        {status === "error" && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-700">{error}</p>
            <button
              type="button"
              onClick={retry}
              className="mt-3 rounded-full bg-red-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
            >
              Retry
            </button>
          </div>
        )}

        {status === "success" && sessions.length === 0 && (
          <div className="rounded-2xl border border-gray-200/80 bg-white p-8 text-center shadow-2xs">
            <p className="text-sm text-gray-500">
              No speaking sessions yet — start practicing to build your
              history.
            </p>
            <Link
              href="/chat"
              className="mt-4 inline-block rounded-full bg-[#0d4d3a] px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-[#09382a]"
            >
              Start a Session
            </Link>
          </div>
        )}

        {status === "success" && sessions.length > 0 && (
          <div className="space-y-6">
            <BandTrendChart sessions={sessions} />
            <SessionHistoryList sessions={sessions} />
          </div>
        )}
      </main>
    </div>
  );
}

function HistoryLoadingSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading session history">
      <div className="h-64 w-full animate-pulse rounded-2xl border border-gray-200/80 bg-gray-100" />
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-16 w-full animate-pulse rounded-2xl border border-gray-200/80 bg-gray-100"
          />
        ))}
      </div>
    </div>
  );
}

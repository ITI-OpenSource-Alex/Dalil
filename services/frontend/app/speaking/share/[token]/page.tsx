"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { usePublicSession } from "@/app/hooks/usePublicSession";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";
import { extractCriteriaScores, formatSessionDate } from "@/lib/speaking-format";

// Deliberately standalone — no <Sidebar>: this page is public and
// unauthenticated, so it must not imply a logged-in nav shell.
export default function PublicSpeakingSessionPage() {
  const params = useParams<{ token: string }>();
  const shareToken = params.token;

  const { session, status, error } = usePublicSession(shareToken);

  return (
    <div className="min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <header className="border-b border-gray-200/80 bg-white px-6 py-4">
        <Link href="/" className="flex items-center gap-2.5 w-fit">
          <div className="w-7 h-7 rounded-full bg-[#0d4d3a] flex items-center justify-center text-white font-serif font-bold text-sm">
            G
          </div>
          <span className="font-serif text-lg font-bold tracking-tight text-[#0d4d3a]">
            goa
          </span>
        </Link>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-12">
        <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
          Shared Speaking Result
        </span>

        {status === "loading" && (
          <div
            className="mt-6 h-72 w-full animate-pulse rounded-2xl border border-gray-200/80 bg-gray-100"
            aria-busy="true"
            aria-label="Loading shared session"
          />
        )}

        {status === "error" && (
          <div className="mt-6 rounded-2xl border border-red-100 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-700">
              {error ??
                "This shared session could not be found. The link may be invalid or no longer available."}
            </p>
          </div>
        )}

        {status === "success" && session && (
          <div className="mt-4 space-y-6">
            <div>
              <h1 className="text-xl font-serif text-gray-900">
                {session.question_prompt}
              </h1>
              <p className="mt-1 text-xs text-gray-400">
                {formatSessionDate(session.created_at)} &bull;{" "}
                {session.question_type}
              </p>
            </div>

            <EvaluationBreakdown
              overallBand={session.overall_band}
              criteria={extractCriteriaScores(session.evaluation)}
              className="rounded-3xl border border-emerald-100 bg-white p-6 shadow-2xs max-w-none"
            />

            {session.transcript && (
              <div className="rounded-3xl border border-gray-200/80 bg-white p-6 shadow-2xs">
                <h3 className="text-sm font-bold uppercase tracking-wide text-gray-400">
                  Transcript
                </h3>
                <p className="mt-3 whitespace-pre-wrap text-sm text-gray-600 leading-relaxed">
                  {session.transcript}
                </p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

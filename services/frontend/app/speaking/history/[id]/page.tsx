"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Sidebar } from "@/components/ui/sidebar";
import { useSessionDetail } from "@/app/hooks/useSessionDetail";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";
import ShareButton from "@/components/speaking/share-button";
import { CURRENT_USER_ID } from "@/lib/current-user";
import { extractCriteriaScores, formatSessionDateTime } from "@/lib/speaking-format";

export default function SpeakingSessionDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = params.id;
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const { session, status, error, retry } = useSessionDetail(
    sessionId,
    CURRENT_USER_ID,
  );

  return (
    <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <Sidebar />

      <main className="flex-1 p-8 md:p-12 max-w-3xl mx-auto">
        <Link
          href="/speaking/history"
          className="mb-6 inline-block text-xs font-semibold text-[#0d4d3a] hover:underline"
        >
          &larr; Back to Session History
        </Link>

        {status === "loading" && (
          <div
            className="h-72 w-full animate-pulse rounded-2xl border border-gray-200/80 bg-gray-100"
            aria-busy="true"
            aria-label="Loading session"
          />
        )}

        {status === "error" && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-700">
              {error ?? "This session could not be found."}
            </p>
            <div className="mt-3 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={retry}
                className="rounded-full bg-red-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
              >
                Retry
              </button>
              <Link
                href="/speaking/history"
                className="rounded-full border border-red-200 px-4 py-1.5 text-xs font-semibold text-red-700 transition hover:bg-red-100"
              >
                Back to History
              </Link>
            </div>
          </div>
        )}

        {status === "success" && session && (
          <div className="space-y-6">
            <div className="rounded-3xl border border-gray-200/80 bg-white p-6 shadow-2xs">
              <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
                {session.question_type}
              </span>
              <h2 className="mt-3 text-xl font-serif text-gray-900">
                {session.question_prompt}
              </h2>
              <p className="mt-1 text-xs text-gray-400">
                {formatSessionDateTime(session.created_at)}
              </p>

              <div className="mt-4">
                <ShareButton sessionId={session.id} />
              </div>
            </div>

            <EvaluationBreakdown
              overallBand={session.overall_band}
              criteria={extractCriteriaScores(session.evaluation)}
              className="rounded-3xl border border-emerald-100 bg-white p-6 shadow-2xs max-w-none"
            />

            {session.transcript && (
              <div className="rounded-3xl border border-gray-200/80 bg-white p-6 shadow-2xs">
                <button
                  type="button"
                  onClick={() => setTranscriptOpen((open) => !open)}
                  aria-expanded={transcriptOpen}
                  className="flex w-full items-center justify-between text-left text-sm font-bold uppercase tracking-wide text-gray-400"
                >
                  Transcript
                  <span aria-hidden="true">{transcriptOpen ? "−" : "+"}</span>
                </button>
                {transcriptOpen && (
                  <p className="mt-3 whitespace-pre-wrap text-sm text-gray-600 leading-relaxed">
                    {session.transcript}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

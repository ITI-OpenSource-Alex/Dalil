"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { SkillArea } from "@/app/types/exam";
import { getResult, getSession } from "@/lib/exam-api";
import { Sidebar } from "@/components/ui/sidebar";
import type { ExamSessionResponse, ExamResultResponse } from "@/lib/exam-api";
import {
  loadReadingResult,
  type StoredReadingResult,
} from "@/lib/reading-result-storage";
import ReadingResultsView from "@/components/reading/results/ReadingResultsView";

// useSearchParams() opts the page into client-side rendering during
// prerendering, which Next.js requires to be wrapped in a Suspense boundary
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout) —
// otherwise `next build`'s static export of this route fails.
export default function ResultsPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ResultsPageContent />
    </Suspense>
  );
}

function ResultsPageContent() {
  const searchParams = useSearchParams();
  const skill = (searchParams.get("skill") || "Reading") as SkillArea;
  const [mounted, setMounted] = useState(false);
  const sessionId = searchParams.get("session") || "";
  const [session, setSession] = useState<ExamSessionResponse | null>(null);
  const [result, setResult] = useState<ExamResultResponse | null>(null);
  const [readingResult, setReadingResult] =
    useState<StoredReadingResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    // Reading has no GET-result endpoint on the backend (see
    // lib/reading-result-storage.ts) — its full per-question breakdown was
    // captured client-side at submit time and only needs to be read back
    // out of sessionStorage, synchronously, no network round trip.
    if (skill === "Reading") {
      const stored = loadReadingResult(sessionId);
      setReadingResult(stored);
      setLoading(false);

      if (!stored) {
        setError("No Reading result found for this session.");
        return;
      }

      sessionStorage.removeItem("active_exam_session");

      return;
    }

    async function loadResult() {
      try {
        setLoading(true);

        const [sessionData, resultData] = await Promise.all([
          getSession(sessionId),
          getResult(sessionId),
        ]);

        setSession(sessionData);
        setResult(resultData);

        sessionStorage.removeItem("active_exam_session");

      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load result");
      } finally {
        setLoading(false);
      }
    }

    loadResult();
  }, [sessionId, skill]);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return <div>{error}</div>;
  }

  if (skill === "Reading") {
    if (!readingResult) {
      return <div>No result found.</div>;
    }

    return (
      <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
        <Sidebar />

        <main className="flex-1 p-8 md:p-12 max-w-5xl mx-auto">
          <div
            className={`transition-all duration-700 ease-out ${
              mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            <ReadingResultsView
              result={readingResult.result}
              questions={readingResult.questions}
            />
          </div>
        </main>
      </div>
    );
  }

  if (!result) {
    return <div>No result found.</div>;
  }

  const sectionScores = Object.entries(result.section_scores).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === "number" && Number.isFinite(entry[1]),
  );
  const weakestSection = [...sectionScores].sort(([, a], [, b]) => a - b)[0];

  return (
    <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <Sidebar />

      <main className="flex-1 p-8 md:p-12 max-w-5xl mx-auto">
        <div
          className={`transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          {/* Result Banner */}
          <div className="bg-white border border-gray-200/80 p-8 rounded-3xl mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center shadow-2xs gap-4">
            <div className="space-y-1">
              <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
                Official Simulation Result
              </span>
              <h2 className="text-2xl md:text-3xl font-serif text-gray-900 mt-2">
                {skill} Analytics
              </h2>
            </div>
            <div className="text-center bg-[#fbfbfa] border border-gray-200/80 rounded-2xl px-6 py-3 shrink-0">
              <p className="text-[10px] uppercase font-bold tracking-widest text-gray-400">
                OVERALL BAND
              </p>
              <p className="text-4xl font-serif font-bold text-[#0d4d3a]">
                {result.band_score}
              </p>
              <p>Raw Score: {result.raw_score}</p>
            </div>
          </div>

          {/* Feedback Feed */}
          <section className="mb-8">
            <h3 className="text-sm font-bold uppercase tracking-wide text-gray-400 mb-4">
              Diagnostic Feed
            </h3>

            {sectionScores.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {sectionScores.map(([section, score]) => (
                  <div key={section} className="border border-gray-200/80 p-5 rounded-2xl bg-white shadow-2xs">
                    <h4 className="font-serif font-bold text-gray-900 text-sm capitalize">
                      {section.replaceAll("_", " ")}
                    </h4>
                    <p className="text-xs text-gray-500 mt-2 leading-relaxed">
                      Score: {score}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500">Detailed section feedback is not available for this result.</p>
            )}
          </section>

          {/* Action Engine Block */}
          <section className="border border-gray-200/80 p-6 bg-white rounded-2xl shadow-2xs">
            <h3 className="text-base font-serif font-bold text-gray-900 mb-3">
              Targeted Action Plan
            </h3>
            <ul className="space-y-2 text-xs text-gray-600 leading-relaxed list-disc pl-4">
              {weakestSection ? (
                <li>
                  <strong>Focus on {weakestSection[0].replaceAll("_", " ")}:</strong>{" "}
                  it is the lowest reported section score ({weakestSection[1]}).
                </li>
              ) : (
                <li>Complete another scored exam to receive a data-backed action plan.</li>
              )}
            </ul>
            <div className="mt-6 pt-4 border-t border-gray-100">
              <Link
                href="/exam"
                className="inline-block bg-[#0d4d3a] hover:bg-[#09382a] text-white font-semibold px-5 py-2.5 rounded-full text-xs transition"
              >
                Return to Skills Workspace
              </Link>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

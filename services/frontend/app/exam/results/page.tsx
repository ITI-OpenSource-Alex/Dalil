"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { SkillArea } from "@/app/types/exam";
import { getResult, getSession } from "@/lib/exam-api";
import { Sidebar } from "@/components/ui/sidebar";
import type { ExamSessionResponse, ExamResultResponse } from "@/lib/exam-api";

export default function ResultsPage() {
  const searchParams = useSearchParams();
  const skill = (searchParams.get("skill") || "Reading") as SkillArea;
  const [mounted, setMounted] = useState(false);
  const sessionId = searchParams.get("session") || "";
  const [session, setSession] = useState<ExamSessionResponse | null>(null);
  const [result, setResult] = useState<ExamResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!sessionId) return;

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

        await fetch("/api/profile/update-scores", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            skill,
            bandScore: resultData.band_score,
          }),
        });
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

  if (!result) {
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

            {skill === "Writing" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-gray-200/80 p-5 rounded-2xl bg-white shadow-2xs">
                  <h4 className="font-serif font-bold text-gray-900 text-sm">
                    Task 1 (Band 7.0)
                  </h4>
                  <p className="text-xs text-gray-500 mt-2 leading-relaxed">
                    Data criteria categorization was logically executed. Minor
                    misalignments identified in structural line summaries.
                  </p>
                </div>
                <div className="border border-gray-200/80 p-5 rounded-2xl bg-white shadow-2xs">
                  <h4 className="font-serif font-bold text-gray-900 text-sm">
                    Task 2 (Band 7.5)
                  </h4>
                  <p className="text-xs text-gray-500 mt-2 leading-relaxed">
                    Arguments presented exhibit robust support structures.
                    Lexical versatility satisfies upper band frameworks.
                  </p>
                </div>
              </div>
            )}
          </section>

          {/* Action Engine Block */}
          <section className="border border-gray-200/80 p-6 bg-white rounded-2xl shadow-2xs">
            <h3 className="text-base font-serif font-bold text-gray-900 mb-3">
              Targeted Action Plan
            </h3>
            <ul className="space-y-2 text-xs text-gray-600 leading-relaxed list-disc pl-4">
              <li>
                <strong>Enhance Cohesion:</strong> Integrate structured
                transition phrases across body paragraphs.
              </li>
              <li>
                <strong>Pacing Thresholds:</strong> Practice under time limits
                to improve writing speed.
              </li>
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
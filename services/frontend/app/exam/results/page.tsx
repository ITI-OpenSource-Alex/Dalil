"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { SkillArea } from "@/app/types/exam";

export default function ResultsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const skill = (searchParams.get("skill") || "Reading") as SkillArea;
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Wipe the session cache upon verified test landing completion sequence
  useEffect(() => {
    sessionStorage.removeItem("active_exam_session");

    // Internal platform update payload pipe simulation (GOA-061 mapping sequence)
    fetch("/api/profile/update-scores", {
      method: "POST",
      body: JSON.stringify({ skill, bandScore: 7.5 }),
    });
  }, [skill]);

  return (
    <div className="min-h-screen bg-linear-to-br from-emerald-50 via-white to-yellow-50 text-black p-6 md:p-12">
      <div
        className={`max-w-4xl mx-auto transition-all duration-700 ease-out ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        {/* Banner Performance Presentation Grid */}
        <div className="border border-gray-200 p-6 md:p-8 rounded-xl mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center bg-yellow-50/40 shadow-sm gap-4">
          <div className="space-y-1">
            <span className="text-xs uppercase font-bold tracking-wider bg-black text-white px-2.5 py-1 rounded">
              Official Simulation Result
            </span>
            <h2 className="text-2xl md:text-3xl font-black tracking-tight text-black uppercase mt-2">
              {skill} Performance Analytics
            </h2>
          </div>
          <div className="text-center bg-white border border-gray-200 rounded-lg px-6 py-3 shadow-2xs shrink-0 w-full sm:w-auto">
            <p className="text-[10px] uppercase font-bold tracking-widest text-gray-400">
              OVERALL BAND
            </p>
            <p className="text-4xl font-black font-mono text-emerald-600">
              7.5
            </p>
          </div>
        </div>

        {/* Variable Interface Output Layout Logic Mapping Per Skill Module Requirements */}
        <section
          className={`mb-10 transition-all duration-700 ease-out delay-150 ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <h3 className="text-lg font-bold uppercase tracking-tight text-black border-b border-gray-200 pb-2 mb-4">
            Diagnostic Review Feed
          </h3>

          {skill === "Speaking" && (
            <div className="space-y-4">
              <div className="border border-gray-200 bg-white rounded-xl p-5 shadow-2xs">
                <h4 className="font-bold text-emerald-700 text-base">
                  Fluency and Coherence (Band 7.0)
                </h4>
                <p className="text-sm mt-1.5 text-gray-700 leading-relaxed">
                  Maintains structural layout stream length without effort. Some
                  repetition noticeable during transition benchmarks into Part 3
                  abstract prompts.
                </p>
                <blockquote className="border-l-4 border-emerald-500 bg-neutral-50 p-3 rounded-r-lg italic text-xs text-gray-600 mt-3">
                  &ldquo;Well, in my perspective, automation might replace...
                  adjust certain structural frameworks...&rdquo;
                </blockquote>
              </div>
              <div className="border border-gray-200 bg-white rounded-xl p-5 shadow-2xs">
                <h4 className="font-bold text-emerald-700 text-base">
                  Lexical Resource (Band 8.0)
                </h4>
                <p className="text-sm mt-1.5 text-gray-700 leading-relaxed">
                  Sophisticated, precise vocabulary handling idiomatic style
                  criteria effectively across descriptive frames.
                </p>
              </div>
            </div>
          )}

          {skill === "Writing" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="border border-gray-200 p-5 rounded-xl bg-white shadow-2xs">
                <h4 className="font-bold text-black border-b border-gray-100 pb-1.5 text-sm uppercase tracking-wide">
                  TASK 1 SUMMARY (Band 7.0)
                </h4>
                <p className="text-xs text-gray-600 mt-2.5 leading-relaxed">
                  Data criteria categorization was logically executed. Minor
                  misalignments identified in structural line summaries.
                </p>
              </div>
              <div className="border border-gray-200 p-5 rounded-xl bg-white shadow-2xs">
                <h4 className="font-bold text-black border-b border-gray-100 pb-1.5 text-sm uppercase tracking-wide">
                  TASK 2 SUMMARY (Band 7.5)
                </h4>
                <p className="text-xs text-gray-600 mt-2.5 leading-relaxed">
                  Arguments presented exhibit robust support criteria
                  structures. Lexical versatility satisfies upper band
                  frameworks smoothly.
                </p>
              </div>
            </div>
          )}

          {(skill === "Reading" || skill === "Listening") && (
            <div className="border border-gray-200 rounded-xl overflow-hidden shadow-2xs divide-y divide-gray-100">
              <div className="p-4 flex justify-between items-center bg-emerald-50/50 text-xs">
                <span className="font-mono font-medium text-gray-700">
                  Question 1 (Locating Information)
                </span>
                <span className="text-emerald-700 font-bold bg-emerald-100/60 px-2 py-0.5 rounded">
                  ✓ Correct (Selected: Paragraph B)
                </span>
              </div>
              <div className="p-4 flex justify-between items-center bg-red-50/40 text-xs">
                <span className="font-mono font-medium text-gray-700">
                  Question 2 (Multiple Choice)
                </span>
                <span className="text-red-700 font-bold bg-red-100/60 px-2 py-0.5 rounded">
                  ✗ Incorrect (Selected: C | Correct Answer: A)
                </span>
              </div>
            </div>
          )}
        </section>

        {/* Standard Actionable Adaptive Improvement Optimization Block */}
        <section
          className={`border border-gray-200 p-6 bg-white rounded-xl shadow-sm transition-all duration-700 ease-out delay-300 ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <h3 className="text-lg font-bold uppercase tracking-wide mb-3 text-emerald-700">
            Targeted Action Plan Engine
          </h3>
          <ul className="space-y-3 text-sm list-disc pl-5 text-gray-600 leading-relaxed">
            <li>
              <strong>Enhance Cohesion Structuring:</strong> Integrate
              structured transitions inside multi-layered syntax frames to
              bypass structural repetition.
            </li>
            <li>
              <strong>Pacing Thresholds Maintenance:</strong> Dedicate timed
              practice drills targeting long-form argumentation pacing limits.
            </li>
            <li>
              <strong>Contextual Review Check:</strong> Isolate complex
              paragraph mappings to minimize minor detail categorization
              mismatches.
            </li>
          </ul>
          <div className="mt-6 pt-5 border-t border-gray-100">
            <Link
              href="/exam"
              className="w-full sm:w-auto inline-block text-center bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-6 py-3 rounded-lg shadow-sm transition-colors duration-200 text-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500"
            >
              RETURN TO SKILLS WORKSPACE TO PRACTICE AGAIN
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}

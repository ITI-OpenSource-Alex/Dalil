"use client";

import { motion } from "framer-motion";
import { Award } from "lucide-react";
import { SpeakingCriteriaScores } from "@/app/types/speaking";

interface EvaluationBreakdownProps {
  /** null when fewer than 3 of the 4 criteria completed (GOA-032, BUG-040). */
  overallBand: number | null;
  criteria: SpeakingCriteriaScores;
  feedback?: string;
  className?: string;
}

/**
 * Shared per-criterion IELTS speaking score display, used by the live chat
 * evaluation panel, the session history detail page, and the public share
 * page — one implementation instead of three diverging copies.
 */
export default function EvaluationBreakdown({
  overallBand,
  criteria,
  feedback,
  className,
}: EvaluationBreakdownProps) {
  const criteriaList = [
    { label: "Fluency & Coherence", score: criteria.fluency },
    { label: "Lexical Resource", score: criteria.lexical },
    { label: "Grammatical Range", score: criteria.grammar },
    { label: "Pronunciation Accuracy", score: criteria.pronunciation },
  ];

  return (
    <div
      className={
        className ??
        "bg-white border border-emerald-100 rounded-xl p-4 shadow-sm max-w-md"
      }
    >
      <div className="flex items-center gap-2 mb-3">
        <Award className="text-emerald-600" size={18} />
        <h4 className="font-bold text-sm text-[#0D3820]">
          IELTS Speaking Band Score
        </h4>
      </div>

      {/* Overall Score Badge */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, delay: 0.15 }}
        className="flex items-center gap-3 bg-emerald-50/50 p-2.5 rounded-lg mb-4"
      >
        <div
          className={`w-12 h-12 rounded-full text-white flex items-center justify-center font-extrabold text-lg ${
            overallBand === null ? "bg-gray-400" : "bg-emerald-600"
          }`}
        >
          {overallBand ?? "—"}
        </div>
        <div>
          <p className="text-xs font-semibold text-[#0E3D23]">
            Estimated Overall Band
          </p>
          <p className="text-[10px] text-[#526053]">
            {overallBand === null
              ? "Not enough criteria completed to score"
              : "Based on criterion rubrics"}
          </p>
        </div>
      </motion.div>

      {/* Criteria Sliders */}
      <div className="space-y-2 mb-3">
        {criteriaList.map((item, idx) => (
          <div key={idx}>
            <div className="flex justify-between text-[11px] font-medium text-[#1D291E]">
              <span>{item.label}</span>
              <span className="font-bold">
                {item.score === null ? "Not scored" : `Band ${item.score}`}
              </span>
            </div>
            <div className="w-full bg-[#F0F3EF] h-1 rounded-full overflow-hidden mt-1">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${((item.score ?? 0) / 9) * 100}%` }}
                transition={{
                  duration: 0.5,
                  delay: 0.2 + idx * 0.08,
                  ease: "easeOut",
                }}
                className="bg-emerald-500 h-full rounded-full"
              />
            </div>
          </div>
        ))}
      </div>

      {feedback && (
        <div className="border-t border-[#EDF1EE] pt-2 mt-2">
          <p className="text-[11px] font-medium text-[#526053]">
            Expert Feedback:
          </p>
          <p className="text-[11px] text-[#526053] leading-relaxed mt-1 italic">
            &ldquo;{feedback}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}

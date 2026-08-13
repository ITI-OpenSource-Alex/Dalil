"use client";

import { motion } from "framer-motion";
import { Award } from "lucide-react";
import { SpeakingCriteriaScores } from "@/app/types/speaking";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

interface EvaluationBreakdownProps {
  /** null when fewer than 3 of the 4 criteria completed (GOA-032, BUG-040). */
  overallBand: number | null;
  criteria: SpeakingCriteriaScores;
  feedback?: string;
  className?: string;
  enableAskDalil?: boolean;
  subjectId?: string;
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
  enableAskDalil = false,
  subjectId,
}: EvaluationBreakdownProps) {
  const criteriaList = [
    { label: "Fluency & Coherence", score: criteria.fluency, note: null },
    { label: "Lexical Resource", score: criteria.lexical, note: null },
    { label: "Grammatical Range", score: criteria.grammar, note: null },
    {
      // GOA-133. Was "Pronunciation Accuracy" -- and accuracy is precisely what
      // this system cannot judge. Assessing phoneme accuracy, word stress or
      // intonation needs acoustic analysis (forced alignment / GOP scoring) that
      // we do not perform. What we measure is speech-recognition confidence and
      // the pause structure, which supports intelligibility and phrasing only.
      //
      // Measured after wiring the real features through: this criterion's band
      // correlates with speech RATE at rho = 0.77, while mean recognition
      // confidence was effectively flat (0.979 vs 0.972). It is a rate-and-
      // chunking judgement, and the old label claimed far more than that.
      //
      // The internal criterion key stays "Pronunciation" -- it is the map key in
      // the swarm payload, the exam service's CriterionDetail, and persisted
      // agent_responses JSONB. Renaming it end to end is a wire and data
      // migration, filed as a follow-up; the user-facing overclaim is the part
      // that had to stop now.
      label: "Intelligibility & Phrasing",
      score: criteria.pronunciation,
      note: "From speech clarity and pausing. Does not assess accent or individual sounds.",
    },
  ];

  return (
    <div
      className={
        className ??
        "bg-surface border border-brand-border rounded-xl p-4 shadow-sm max-w-md"
      }
    >
      <div className="flex items-center gap-2 mb-3">
        <Award className="text-brand-fg" size={18} aria-hidden="true" />
        <h4 className="font-bold text-sm text-brand-fg">
          IELTS Speaking Band Score
        </h4>
      </div>

      {/* Overall Score Badge */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, delay: 0.15 }}
        className="flex items-center gap-3 bg-brand-subtle p-2.5 rounded-lg mb-4"
      >
        <div
          className={`w-12 h-12 rounded-full text-white flex items-center justify-center font-extrabold text-lg ${
            overallBand === null ? "bg-fg-subtle" : "bg-brand"
          }`}
        >
          {overallBand ?? "—"}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-brand-fg">
            Estimated Overall Band
          </p>
          <p className="text-[10px] text-fg-muted">
            {overallBand === null
              ? "Not enough criteria completed to score"
              : "Based on criterion rubrics"}
          </p>
        </div>
        {enableAskDalil && overallBand !== null && (
          <ExplainWithDalilButton
            context={{
              kind: "speaking_score",
              title: `your estimated speaking band ${overallBand}`,
              subjectId,
              summary: "An IELTS speaking practice estimate based on completed criterion rubrics.",
              facts: compactFacts([
                fact("Estimated overall band", overallBand),
                fact("Fluency and coherence", criteria.fluency),
                fact("Lexical resource", criteria.lexical),
                fact("Grammatical range", criteria.grammar),
                fact("Intelligibility and phrasing", criteria.pronunciation),
                fact("Evaluator feedback", feedback),
              ]),
              limitations: [
                "This is a practice estimate, not an official IELTS result.",
                "Intelligibility and phrasing does not assess accent or individual phoneme accuracy.",
              ],
            }}
            prompt={`Why is my estimated IELTS Speaking band ${overallBand}? Explain how each scored criterion contributed and what would most improve it.`}
          />
        )}
      </motion.div>

      {/* Criteria Sliders */}
      <div className="space-y-2 mb-3">
        {criteriaList.map((item, idx) => (
          <div key={idx}>
            <div className="flex items-center justify-between gap-2 text-[11px] font-medium text-fg">
              <span>{item.label}</span>
              <span className="flex items-center gap-1.5">
                <span className="font-bold">
                  {item.score === null ? "Not scored" : `Band ${item.score}`}
                </span>
                {enableAskDalil && item.score !== null && (
                  <ExplainWithDalilButton
                    context={{
                      kind: "speaking_score",
                      title: `${item.label} band ${item.score}`,
                      subjectId,
                      facts: compactFacts([
                        fact("Criterion", item.label),
                        fact("Estimated criterion band", item.score),
                        fact("Estimated overall band", overallBand),
                        fact("Evaluator feedback", feedback),
                        fact("Measurement note", item.note),
                      ]),
                      limitations: item.note
                        ? [item.note, "This is a practice estimate, not an official IELTS result."]
                        : ["This is a practice estimate, not an official IELTS result."],
                    }}
                    prompt={`Why did I receive band ${item.score} for ${item.label}? Explain the evidence, what kept it from the next band, and one focused practice step.`}
                  />
                )}
              </span>
            </div>
            <div className="w-full bg-canvas-inset h-1 rounded-full overflow-hidden mt-1">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${((item.score ?? 0) / 9) * 100}%` }}
                transition={{
                  duration: 0.5,
                  delay: 0.2 + idx * 0.08,
                  ease: "easeOut",
                }}
                className="bg-brand h-full rounded-full"
              />
            </div>
            {item.note && (
              <p className="text-[10px] text-[#7A8A7D] leading-snug mt-1">
                {item.note}
              </p>
            )}
          </div>
        ))}
      </div>

      {feedback && (
        <div className="border-t border-border pt-2 mt-2">
          <p className="text-[11px] font-medium text-fg-muted">
            Expert Feedback:
          </p>
          <p className="text-[11px] text-fg-muted leading-relaxed mt-1 italic">
            &ldquo;{feedback}&rdquo;
          </p>
        </div>
      )}
    </div>
  );
}

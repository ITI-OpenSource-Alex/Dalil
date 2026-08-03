"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  PenSquare,
  Lock,
  Download,
  FileText,
  Sparkles,
} from "lucide-react";
import type { CriterionEvaluation } from "@/lib/writing-api";
import EssayHighlighter, { EssayIssue } from "./essay-highlighter";

interface SimpleCriterionScore {
  band: number;
  feedback: string;
}

interface WritingEvaluationPanelProps {
  evaluations: Record<string, SimpleCriterionScore>;
  overallBand?: number;
  loading?: boolean;
  essayText?: string;
  inlineIssues?: CriterionEvaluation[];
  improvedEssay?: string; // paid tier
  isPaidTier?: boolean;
}

const labels: Record<string, string> = {
  task_achievement: "Task Achievement",
  coherence: "Coherence & Cohesion",
  lexical: "Lexical Resource",
  grammar: "Grammatical Range & Accuracy",
};

// Normalizes the two parallel naming schemes in use across the API
// (evaluations map: task_achievement/coherence/lexical/grammar,
// CriterionEvaluation.criterion: task_response/cohesion/vocabulary/grammar)
// onto one canonical key so colours line up everywhere.
const CRITERION_ALIASES: Record<string, string> = {
  task_achievement: "task_response",
  task_response: "task_response",
  coherence: "cohesion",
  cohesion: "cohesion",
  lexical: "vocabulary",
  vocabulary: "vocabulary",
  grammar: "grammar",
};

const BAR_COLOURS: Record<string, string> = {
  task_response: "#8B5CF6",
  cohesion: "#FF8C00",
  vocabulary: "#3B82F6",
  grammar: "#FF4D4D",
};

const DEFAULT_BAR_COLOUR = "#059669"; // emerald-600 fallback

function getBarColour(key: string): string {
  const canonical = CRITERION_ALIASES[key] ?? key;
  return BAR_COLOURS[canonical] ?? DEFAULT_BAR_COLOUR;
}

type EssayView = "original" | "improved";

export default function WritingEvaluationPanel({
  evaluations,
  overallBand,
  loading = false,
  essayText,
  inlineIssues = [],
  improvedEssay,
  isPaidTier = false,
}: WritingEvaluationPanelProps) {
  const [essayView, setEssayView] = useState<EssayView>("original");

  const essayIssues: EssayIssue[] = inlineIssues.flatMap((evaluation) =>
    evaluation.highlighted_issues.map((issue) => ({
      ...issue,
      criterion: evaluation.criterion,
    })),
  );

  const canShowImproved = isPaidTier && !!improvedEssay;

  return (
    <motion.div
      id="writing-evaluation-panel"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#E4EAE4] bg-white shadow-sm p-5 space-y-5"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PenSquare className="text-emerald-600" size={18} />
          <h3 className="font-semibold text-[#16351F]">
            IELTS Writing Evaluation
          </h3>
        </div>

        <button
          type="button"
          onClick={() => window.print()}
          className="print-hide flex items-center gap-1.5 text-xs font-medium text-[#526053] border border-[#E4EAE4] rounded-md px-2.5 py-1.5 hover:bg-[#F5F8F5] transition-colors"
        >
          <Download size={14} />
          Download PDF
        </button>
      </div>

      <div className="space-y-4">
        <AnimatePresence>
          {Object.entries(evaluations).map(([key, value]) => {
            const barColour = getBarColour(key);

            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="space-y-2"
              >
                <div className="flex justify-between">
                  <span className="text-sm font-medium text-[#1D291E]">
                    {labels[key] ?? key}
                  </span>

                  <span className="font-bold" style={{ color: barColour }}>
                    Band {value.band.toFixed(1)}
                  </span>
                </div>

                <div className="h-2 rounded-full bg-[#EEF2EE] overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{
                      width: `${(value.band / 9) * 100}%`,
                    }}
                    transition={{ duration: 0.4 }}
                    className="h-full"
                    style={{ background: barColour }}
                  />
                </div>

                <p className="text-xs text-[#667267] leading-relaxed">
                  {value.feedback}
                </p>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {loading && (
        <div className="text-sm text-[#6C7A6E] animate-pulse">
          Evaluating essay...
        </div>
      )}

      {overallBand !== undefined && (
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="border-t pt-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="text-emerald-600" size={18} />
            <span className="font-semibold">Estimated Overall Band</span>
          </div>

          <span className="text-xl font-bold text-emerald-700">
            {overallBand.toFixed(1)}
          </span>
        </motion.div>
      )}

      {essayText && (
        <div className="border-t pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="text-[#526053]" size={16} />
              <span className="text-sm font-semibold text-[#1D291E]">
                Essay with Inline Highlights
              </span>
            </div>

            <div className="print-hide flex items-center rounded-md border border-[#E4EAE4] p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setEssayView("original")}
                className={`px-2.5 py-1 rounded ${
                  essayView === "original"
                    ? "bg-[#16351F] text-white"
                    : "text-[#526053] hover:bg-[#F5F8F5]"
                }`}
              >
                Original
              </button>
              <button
                type="button"
                onClick={() => isPaidTier && setEssayView("improved")}
                disabled={!isPaidTier}
                title={
                  isPaidTier
                    ? undefined
                    : "Upgrade to a paid plan to unlock the improved essay"
                }
                className={`flex items-center gap-1 px-2.5 py-1 rounded ${
                  essayView === "improved" && isPaidTier
                    ? "bg-[#16351F] text-white"
                    : "text-[#A2ADA3] cursor-not-allowed"
                }`}
              >
                {!isPaidTier && <Lock size={11} />}
                Improved
              </button>
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto rounded-md border border-[#E4EAE4] bg-[#FAFBF9] p-3">
            {essayView === "improved" && canShowImproved ? (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                  <Sparkles size={12} />
                  Improved version
                </div>
                <p className="text-sm text-[#1D291E] leading-relaxed whitespace-pre-wrap">
                  {improvedEssay}
                </p>
              </div>
            ) : (
              <EssayHighlighter essayText={essayText} issues={essayIssues} />
            )}
          </div>
        </div>
      )}

      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #writing-evaluation-panel,
          #writing-evaluation-panel * {
            visibility: visible;
          }
          #writing-evaluation-panel {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            box-shadow: none;
            border: none;
          }
          #writing-evaluation-panel .print-hide {
            display: none !important;
          }
        }
      `}</style>
    </motion.div>
  );
}
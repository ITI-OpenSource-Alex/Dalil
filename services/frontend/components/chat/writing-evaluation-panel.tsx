"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, PenSquare } from "lucide-react";

export interface CriterionEvaluation {
  band: number;
  feedback: string;
}

interface WritingEvaluationPanelProps {
  evaluations: Record<string, CriterionEvaluation>;
  overallBand?: number;
  loading?: boolean;
}

const labels: Record<string, string> = {
  task_achievement: "Task Achievement",
  coherence: "Coherence & Cohesion",
  lexical: "Lexical Resource",
  grammar: "Grammatical Range & Accuracy",
};

export default function WritingEvaluationPanel({
  evaluations,
  overallBand,
  loading = false,
}: WritingEvaluationPanelProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[#E4EAE4] bg-white shadow-sm p-5 space-y-5"
    >
      <div className="flex items-center gap-2">
        <PenSquare className="text-emerald-600" size={18} />
        <h3 className="font-semibold text-[#16351F]">
          IELTS Writing Evaluation
        </h3>
      </div>

      <div className="space-y-4">
        <AnimatePresence>
          {Object.entries(evaluations).map(([key, value]) => (
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

                <span className="font-bold text-emerald-700">
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
                  className="h-full bg-emerald-600"
                />
              </div>

              <p className="text-xs text-[#667267] leading-relaxed">
                {value.feedback}
              </p>
            </motion.div>
          ))}
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
    </motion.div>
  );
}

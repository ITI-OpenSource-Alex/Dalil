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
import InlineAlert from "@/components/speaking/inline-alert";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

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
  /** Set when the evaluation stream failed to open or errored mid-stream. */
  error?: string | null;
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

const DEFAULT_BAR_COLOUR = "var(--color-success)";

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
  error = null,
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
      className="rounded-xl border border-border bg-surface shadow-sm p-5 space-y-5"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <PenSquare className="text-brand-fg" size={18} aria-hidden="true" />
          <h2 className="font-semibold text-brand-fg">
            IELTS Writing Evaluation
          </h2>
        </div>

        <button
          type="button"
          data-testid="download-pdf-button"
          onClick={() => window.print()}
          className="print-hide flex items-center gap-1.5 text-xs font-medium text-fg-muted border border-border rounded-md px-2.5 py-1.5 hover:bg-canvas-subtle transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
        >
          <Download size={14} aria-hidden="true" />
          Download PDF
        </button>
      </div>

      {error && (
        <InlineAlert
          title="Essay evaluation failed"
          description={error}
        />
      )}

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
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-fg">
                    {labels[key] ?? key}
                  </span>

                  <span className="flex items-center gap-1.5">
                    <span className="font-bold" style={{ color: barColour }}>
                      Band {value.band.toFixed(1)}
                    </span>
                    <ExplainWithDalilButton
                      context={{
                        kind: "writing_score",
                        title: `${labels[key] ?? key} writing band ${value.band.toFixed(1)}`,
                        facts: compactFacts([
                          fact("Criterion", labels[key] ?? key),
                          fact("Estimated criterion band", value.band.toFixed(1)),
                          fact("Estimated overall band", overallBand?.toFixed(1)),
                          fact("Evaluator feedback", value.feedback),
                        ]),
                        limitations: [
                          "This is an AI-assisted practice estimate, not an official IELTS result.",
                        ],
                      }}
                      prompt={`Why did my ${labels[key] ?? key} receive band ${value.band.toFixed(1)}? Explain the feedback in plain language and give me one before-and-after example of how to improve it.`}
                    />
                  </span>
                </div>

                <div className="h-2 rounded-full bg-canvas-inset overflow-hidden">
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

                <p className="text-xs text-fg-muted leading-relaxed">
                  {value.feedback}
                </p>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {loading && (
        <div className="text-sm text-fg-muted animate-pulse">
          Evaluating essay...
        </div>
      )}

      {overallBand !== undefined && (
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="border-t border-border pt-4 flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="text-success-fg" size={18} aria-hidden="true" />
            <span className="font-semibold">Estimated Overall Band</span>
          </div>

          <span className="flex items-center gap-2">
            <span className="text-xl font-bold text-success-fg">
              {overallBand.toFixed(1)}
            </span>
            <ExplainWithDalilButton
              context={{
                kind: "writing_score",
                title: `your estimated overall writing band ${overallBand.toFixed(1)}`,
                facts: compactFacts([
                  fact("Estimated overall band", overallBand.toFixed(1)),
                  ...Object.entries(evaluations).map(([key, value]) =>
                    fact(`${labels[key] ?? key} band`, value.band.toFixed(1)),
                  ),
                ]),
                limitations: [
                  "This is an AI-assisted practice estimate, not an official IELTS result.",
                ],
              }}
              prompt={`Explain why my estimated overall Writing band is ${overallBand.toFixed(1)}. Which criterion is limiting it most, and what should I work on first?`}
            />
          </span>
        </motion.div>
      )}

      {essayText && (
        <div className="border-t border-border pt-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="text-fg-muted" size={16} aria-hidden="true" />
              <span className="text-sm font-semibold text-fg">
                Essay with Inline Highlights
              </span>
            </div>

            <div
              className="print-hide flex items-center rounded-md border border-border p-0.5 text-xs"
              role="tablist"
              aria-label="Essay view"
            >
              <button
                type="button"
                role="tab"
                aria-selected={essayView === "original"}
                onClick={() => setEssayView("original")}
                className={`px-2.5 py-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted ${
                  essayView === "original"
                    ? "bg-brand text-fg-on-brand"
                    : "text-fg-muted hover:bg-canvas-subtle"
                }`}
              >
                Original
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={essayView === "improved" && isPaidTier}
                onClick={() => isPaidTier && setEssayView("improved")}
                disabled={!isPaidTier}
                title={
                  isPaidTier
                    ? undefined
                    : "Upgrade to a paid plan to unlock the improved essay"
                }
                className={`flex items-center gap-1 px-2.5 py-1 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted ${
                  essayView === "improved" && isPaidTier
                    ? "bg-brand text-fg-on-brand"
                    : "text-fg-subtle cursor-not-allowed"
                }`}
              >
                {!isPaidTier && <Lock size={11} aria-hidden="true" />}
                Improved
              </button>
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto rounded-md border border-border bg-canvas-subtle p-3">
            {essayView === "improved" && canShowImproved ? (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-medium text-brand-fg">
                  <Sparkles size={12} aria-hidden="true" />
                  Improved version
                </div>
                <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap">
                  {improvedEssay}
                </p>
              </div>
            ) : (
              <EssayHighlighter essayText={essayText} issues={essayIssues} />
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}

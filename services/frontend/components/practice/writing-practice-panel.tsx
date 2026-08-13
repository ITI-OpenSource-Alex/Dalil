"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import EssayComposer from "@/components/chat/essay-composer";
import WritingEvaluationPanel from "@/components/chat/writing-evaluation-panel";
import { createEssay } from "@/lib/writing-practice-api";
import { streamWritingEvaluation, WritingEvent } from "@/lib/writing-stream";
import type { CriterionEvaluation } from "@/lib/writing-api";
import { sanitizeErrorMessage } from "@/lib/chat-sanitize";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";

const GATEWAY_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

/**
 * Writing Practice, standalone. Reuses the exact composer/evaluation
 * components Chat used to host inline (components/chat/essay-composer.tsx,
 * writing-evaluation-panel.tsx) and the same SSE client
 * (lib/writing-stream.ts), but creates the essay directly via
 * POST /api/writing/essays/upload instead of going through Chat's
 * /api/chat + LLM intent-classification pipeline. Writing Practice no
 * longer needs a classifier to decide the user wants to practice writing --
 * they're already on this page.
 */
export default function WritingPracticePanel() {
  const searchParams = useSearchParams();
  const upgrade = useUpgradePrompt();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluations, setEvaluations] = useState<
    Record<string, { band: number; feedback: string }>
  >({});
  const [overallBand, setOverallBand] = useState<number>();
  const [inlineIssues, setInlineIssues] = useState<CriterionEvaluation[]>([]);
  const [submittedEssay, setSubmittedEssay] = useState("");
  const [improvedEssay, setImprovedEssay] = useState<string | undefined>();
  // TODO: hardcoded until tier comes from session/profile -- same open item
  // as the chat-embedded version this replaces (components/chat/chat-shell.tsx).
  const [isPaidTier] = useState(true);

  function handleEvent(event: WritingEvent) {
    switch (event.type) {
      case "criterion":
        setEvaluations((prev) => ({
          ...prev,
          [event.criterion]: { band: event.band, feedback: event.feedback },
        }));
        break;
      case "complete":
        setEvaluations(event.evaluations);
        setOverallBand(event.overall_band);
        setInlineIssues(event.evaluations_full);
        setImprovedEssay(event.improved_essay);
        setLoading(false);
        break;
      case "error":
        console.error(event.error);
        setLoading(false);
        setError(event.error);
        break;
    }
  }

  function evaluate(essayId: string | number) {
    const sseUrl = `${GATEWAY_BASE}/api/writing/essays/${essayId}/evaluate`;
    streamWritingEvaluation(sseUrl, handleEvent).catch((err) => {
      setLoading(false);
      if (upgrade.handle(err, "essay-evaluation")) {
        setError("Essay evaluation is part of Dalil Pro — see the upgrade details.");
        return;
      }
      console.error(err);
      setError(sanitizeErrorMessage(err instanceof Error ? err.message : undefined));
    });
  }

  // Deep link from Chat: orchestration already created the essay (see
  // handleChatEvent's writing_url case in chat-shell.tsx) and handed the
  // browser its id via ?essayId=. Picking that essay up here instead of
  // creating a second one is what makes the essay text a user already typed
  // in Chat not go to waste.
  useEffect(() => {
    const essayId = searchParams.get("essayId");
    if (!essayId) return;
    setLoading(true);
    setError(null);
    evaluate(essayId);
    // Only ever acts on the id present on the page's first render -- this
    // is a one-time handoff, not a value to keep re-reacting to.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(essay: string) {
    setEvaluations({});
    setOverallBand(undefined);
    setInlineIssues([]);
    setImprovedEssay(undefined);
    setSubmittedEssay(essay);
    setError(null);
    setLoading(true);

    try {
      const { id } = await createEssay(essay, "task2");
      evaluate(id);
    } catch (err) {
      setLoading(false);
      if (upgrade.handle(err, "writing-practice")) {
        setError("Writing Practice is part of Dalil Pro — see the upgrade details.");
        return;
      }
      console.error(err);
      setError(sanitizeErrorMessage(err instanceof Error ? err.message : undefined));
    }
  }

  return (
    <div className="space-y-4">
      <EssayComposer loading={loading} onSubmit={handleSubmit} />
      <WritingEvaluationPanel
        evaluations={evaluations}
        overallBand={overallBand}
        loading={loading}
        inlineIssues={inlineIssues}
        essayText={submittedEssay}
        improvedEssay={improvedEssay}
        isPaidTier={isPaidTier}
        error={error}
      />
    </div>
  );
}

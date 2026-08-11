"use client";

import Link from "next/link";
import { Lightbulb } from "lucide-react";
import { useExamProgress } from "@/app/hooks/useExamProgress";
import { Button, Card, Icon, Text } from "@/components/ui";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

const SKILL_LABEL: Record<string, string> = {
  reading: "Reading",
  listening: "Listening",
  speaking: "Speaking",
  writing: "Writing",
};

// Reading and Listening have no free-form practice mode -- IELTS Exam is the
// only way to attempt either, so both recommendations point back at it.
const SKILL_HREF: Record<string, string> = {
  reading: "/exam",
  listening: "/exam",
  speaking: "/practice/speaking",
  writing: "/practice/writing",
};

/**
 * "Upcoming recommendations (if data exists)" -- derived from the user's own
 * exam attempts (their lowest-scored skill), not fabricated content. Renders
 * nothing at all, not even an empty state, when there isn't enough data to
 * say anything honest: a Free account, or a Pro account that hasn't sat an
 * exam yet, simply doesn't get this widget on their Dashboard.
 */
export function RecommendationsWidget() {
  const { progress, status } = useExamProgress();

  if (status !== "success") return null;

  const latestBySkill = Object.entries(progress)
    .filter(([, entries]) => (entries?.length ?? 0) > 0)
    .map(([skill, entries]) => ({
      skill,
      band: entries!.reduce((a, b) => (a.date > b.date ? a : b)).band,
    }));

  if (latestBySkill.length === 0) return null;

  const weakest = latestBySkill.reduce((a, b) => (a.band <= b.band ? a : b));
  const label = SKILL_LABEL[weakest.skill] ?? weakest.skill;
  const href = SKILL_HREF[weakest.skill] ?? "/exam";

  return (
    <Card className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
          <Icon icon={Lightbulb} size="sm" />
        </span>
        <div>
          <Text size="sm" weight="semibold">
            Recommended for you
          </Text>
          <Text size="sm" tone="muted" className="mt-0.5">
            {label} is your lowest-scored skill right now (band{" "}
            {weakest.band.toFixed(1)}) — a bit more practice here could lift
            your overall band.
          </Text>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <ExplainWithDalilButton
          display="compact"
          context={{
            kind: "recommendation",
            title: `the recommendation to practise ${label}`,
            summary: `${label} is currently the lowest latest skill band.`,
            facts: compactFacts([
              fact("Recommended skill", label),
              fact("Latest band", weakest.band.toFixed(1)),
              ...latestBySkill.map((entry) =>
                fact(`${SKILL_LABEL[entry.skill] ?? entry.skill} latest band`, entry.band.toFixed(1)),
              ),
            ]),
            limitations: [
              "The recommendation compares only the latest recorded attempt for each available skill.",
            ],
          }}
          prompt={`Why are you recommending ${label} practice based on my latest bands? Explain the comparison and suggest a focused next session.`}
        />
        <Button size="sm" asChild>
          <Link href={href}>Practice {label}</Link>
        </Button>
      </div>
    </Card>
  );
}

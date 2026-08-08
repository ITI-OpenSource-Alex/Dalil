"use client";

import Link from "next/link";
import { GraduationCap, Sparkles } from "lucide-react";
import { useExamProgress } from "@/app/hooks/useExamProgress";
import { Button, Card, EmptyState, Skeleton, Text } from "@/components/ui";

const SKILLS: { key: "reading" | "listening" | "speaking" | "writing"; label: string }[] = [
  { key: "reading", label: "Reading" },
  { key: "listening", label: "Listening" },
  { key: "speaking", label: "Speaking" },
  { key: "writing", label: "Writing" },
];

export function IeltsSummaryWidget() {
  const { progress, status } = useExamProgress();

  if (status === "loading" || status === "idle") {
    return (
      <Card>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-14 w-full" />
      </Card>
    );
  }

  if (status === "upgrade-required") {
    return (
      <Card>
        <Text size="sm" tone="muted" className="mb-2 font-semibold">
          IELTS summary
        </Text>
        <EmptyState
          icon={Sparkles}
          title="IELTS scoring is part of GOA Pro"
          description="Upgrade to sit full practice exams and track your band scores here."
          size="sm"
          actions={
            <Button size="sm" asChild>
              <Link href="/exam">See IELTS Exam</Link>
            </Button>
          }
        />
      </Card>
    );
  }

  if (status === "error") return null;

  const attempted = SKILLS.filter((skill) => (progress[skill.key]?.length ?? 0) > 0);

  if (attempted.length === 0) {
    return (
      <Card>
        <Text size="sm" tone="muted" className="mb-2 font-semibold">
          IELTS summary
        </Text>
        <EmptyState
          icon={GraduationCap}
          title="No exam attempts yet"
          description="Sit a full timed skill exam to see your band scores here."
          size="sm"
          actions={
            <Button size="sm" asChild>
              <Link href="/exam">Take an exam</Link>
            </Button>
          }
        />
      </Card>
    );
  }

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between gap-3">
        <Text size="sm" tone="muted" className="font-semibold">
          IELTS summary
        </Text>
        <Button variant="link" size="sm" asChild>
          <Link href="/exam">View exam</Link>
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {SKILLS.map((skill) => {
          const entries = progress[skill.key];
          const latest = entries?.length
            ? entries.reduce((a, b) => (a.date > b.date ? a : b))
            : null;
          return (
            <div key={skill.key}>
              <Text size="xs" tone="subtle">
                {skill.label}
              </Text>
              <Text size="lg" weight="semibold" className="mt-1">
                {latest ? latest.band.toFixed(1) : "—"}
              </Text>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

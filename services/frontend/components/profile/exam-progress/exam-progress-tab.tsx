"use client";

import Link from "next/link";
import { GraduationCap, Sparkles } from "lucide-react";
import { useExamProgressTab } from "@/app/hooks/useExamProgressTab";
import {
  Alert,
  Button,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { EstimatedOverallBand } from "./estimated-overall-band";
import { RecentExamsList } from "./recent-exams-list";
import { SkillTrendChart } from "./skill-trend-chart";
import { WeakAreasPanel } from "./weak-areas-panel";

function ExamProgressLoading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading exam progress">
      <Skeleton className="h-24 w-full rounded-card" />
      <Skeleton className="h-72 w-full rounded-card" />
      <Skeleton className="h-20 w-full rounded-card" />
      <Skeleton className="h-28 w-full rounded-card" />
    </div>
  );
}

export function ExamProgressTab() {
  const {
    progress,
    history,
    weakAreas,
    progressError,
    historyError,
    weakAreasError,
    tab,
    retry,
  } = useExamProgressTab();

  if (tab === "loading") {
    return <ExamProgressLoading />;
  }

  if (tab === "upgrade-required") {
    return (
      <EmptyState
        icon={Sparkles}
        title="Exam progress is part of GOA Pro"
        description="Upgrade to sit full practice exams and track your band scores here."
        bordered
        actions={
          <Button size="sm" asChild>
            <Link href="/exam">See IELTS Exam</Link>
          </Button>
        }
      />
    );
  }

  if (tab === "empty") {
    return (
      <EmptyState
        icon={GraduationCap}
        title="No practice exams yet"
        description="Sit a timed IELTS practice exam to see band trends, weak areas, and recent results here."
        bordered
        actions={
          <Button size="sm" asChild>
            <Link href="/exam" data-testid="exam-progress-empty-cta">
              Start your first practice exam
            </Link>
          </Button>
        }
      />
    );
  }

  if (tab === "hard-error") {
    return (
      <Alert
        tone="danger"
        title="Couldn't load exam progress"
        actions={
          <Button variant="danger" size="sm" onClick={() => void retry()}>
            Retry
          </Button>
        }
      >
        {progressError || historyError || "Please try again."}
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {progressError && (
        <Alert
          tone="warning"
          title="Couldn't load band trends"
          actions={
            <Button size="sm" variant="secondary" onClick={() => void retry()}>
              Retry
            </Button>
          }
        >
          {progressError}
        </Alert>
      )}
      {historyError && (
        <Alert
          tone="warning"
          title="Couldn't load recent exams"
          actions={
            <Button size="sm" variant="secondary" onClick={() => void retry()}>
              Retry
            </Button>
          }
        >
          {historyError}
        </Alert>
      )}

      {!progressError && <EstimatedOverallBand progress={progress} />}
      {!progressError && <SkillTrendChart progress={progress} />}
      <WeakAreasPanel
        weakAreas={weakAreas}
        error={weakAreasError}
        onRetry={() => void retry()}
      />
      {!historyError && <RecentExamsList items={history.slice(0, 5)} />}
    </div>
  );
}

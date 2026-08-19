"use client";

import Link from "next/link";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import SessionHistoryList from "@/components/speaking/session-history-list";
import BandTrendChart from "@/components/speaking/band-trend-chart";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Heading,
  PageContainer,
  Skeleton,
} from "@/components/ui";
import { History } from "lucide-react";

export default function SpeakingHistoryPage() {
  const { sessions, status, error, retry } = useSessionHistory();

  return (
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            Speaking Practice
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            Session History
          </Heading>
        </div>
        <Button size="sm" asChild className="shrink-0">
          <Link href="/practice/speaking">Practice Again</Link>
        </Button>
      </div>

      {status === "loading" && <HistoryLoadingSkeleton />}

      {status === "error" && (
        <Alert
          tone="danger"
          actions={
            <Button variant="danger" size="sm" onClick={retry}>
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {status === "success" && sessions.length === 0 && (
        <EmptyState
          icon={History}
          title="No speaking sessions yet"
          description="Start practicing to build your history."
          actions={
            <Button size="sm" asChild>
              <Link href="/practice/speaking">Start a Session</Link>
            </Button>
          }
        />
      )}

      {status === "success" && sessions.length > 0 && (
        <div className="space-y-6">
          <BandTrendChart sessions={sessions} />
          <SessionHistoryList sessions={sessions} />
        </div>
      )}
    </PageContainer>
  );
}

function HistoryLoadingSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading session history">
      <Skeleton shape="block" className="h-64 w-full" />
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} shape="block" className="h-16 w-full" />
        ))}
      </div>
    </div>
  );
}

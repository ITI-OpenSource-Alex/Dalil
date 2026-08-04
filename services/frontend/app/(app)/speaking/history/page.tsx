"use client";

import Link from "next/link";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import SessionHistoryList from "@/components/speaking/session-history-list";
import BandTrendChart from "@/components/speaking/band-trend-chart";
import { Alert, Badge, Button, Card, Heading, PageContainer, Text } from "@/components/ui";

export default function SpeakingHistoryPage() {
  const { sessions, status, error, retry } = useSessionHistory();

  return (
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            Speaking Practice
          </Badge>
          <Heading as="h2" size="xl" className="mt-2">
            Session History
          </Heading>
        </div>
        <Button size="sm" asChild className="shrink-0">
          <Link href="/chat">Practice Again</Link>
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
        <Card className="text-center">
          <Text size="sm" tone="muted">
            No speaking sessions yet — start practicing to build your
            history.
          </Text>
          <Button size="sm" asChild className="mt-4">
            <Link href="/chat">Start a Session</Link>
          </Button>
        </Card>
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
      <div className="h-64 w-full animate-pulse rounded-card border border-border bg-canvas-inset" />
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-16 w-full animate-pulse rounded-card border border-border bg-canvas-inset"
          />
        ))}
      </div>
    </div>
  );
}

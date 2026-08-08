"use client";

import Link from "next/link";
import { useWritingHistory } from "@/app/hooks/useWritingHistory";
import { formatSessionDateTime } from "@/lib/speaking-format";
import { EssayHistoryItem } from "@/app/types/writing";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Heading,
  PageContainer,
  Skeleton,
  Text,
} from "@/components/ui";
import { PenSquare } from "lucide-react";

/**
 * Writing History, wired to GET /api/writing/essays (Phase B). The backend
 * only returns a paged summary -- id, date, status, band, a short excerpt --
 * with no per-essay detail endpoint yet, so this is list-only: no click-
 * through to a detail page, no trend chart (no generated overall_band column
 * exposed to the ORM yet -- see services/writing/app/models.py), and no
 * "previous rewrites" (not persisted -- see docs/IA-REDESIGN-PROPOSAL.md
 * §9.1). Building any of those now would mean inventing data the backend
 * doesn't provide.
 */
export default function WritingHistoryPage() {
  const { essays, status, error, retry } = useWritingHistory();

  return (
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            Writing Practice
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            Essay History
          </Heading>
        </div>
        <Button size="sm" asChild className="shrink-0">
          <Link href="/practice/writing">Practice Again</Link>
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

      {status === "success" && essays.length === 0 && (
        <EmptyState
          icon={PenSquare}
          title="No essays yet"
          description="Start practicing to build your history."
          actions={
            <Button size="sm" asChild>
              <Link href="/practice/writing">Start Writing</Link>
            </Button>
          }
        />
      )}

      {status === "success" && essays.length > 0 && (
        <div className="space-y-3">
          {essays.map((essay) => (
            <EssayRow key={essay.id} essay={essay} />
          ))}
        </div>
      )}
    </PageContainer>
  );
}

function EssayRow({ essay }: { essay: EssayHistoryItem }) {
  return (
    <Card className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral" size="sm">
            {essay.submission_type ?? "practice"}
          </Badge>
          <Text size="xs" tone="subtle">
            {formatSessionDateTime(essay.submitted_at)}
          </Text>
        </div>
        <Text size="sm" tone="muted" className="mt-1.5 line-clamp-2">
          {essay.excerpt}
        </Text>
      </div>
      <div className="shrink-0 text-right">
        <Text size="xs" tone="subtle">
          Band
        </Text>
        <p className="text-lg font-bold text-fg tabular-nums">
          {essay.overall_band !== null ? essay.overall_band.toFixed(1) : "—"}
        </p>
      </div>
    </Card>
  );
}

function HistoryLoadingSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading essay history">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} shape="block" className="h-20 w-full" />
      ))}
    </div>
  );
}

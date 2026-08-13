"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSessionDetail } from "@/app/hooks/useSessionDetail";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";
import ShareButton from "@/components/speaking/share-button";
import { extractCriteriaScores, formatSessionDateTime } from "@/lib/speaking-format";
import { Alert, Badge, Button, Card, Heading, PageContainer, Skeleton, Text } from "@/components/ui";

export default function SpeakingSessionDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = params.id;
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const { session, status, error, retry } = useSessionDetail(sessionId);

  return (
    <PageContainer size="md">
      <Button variant="link" size="sm" asChild className="mb-6">
        <Link href="/practice/speaking/history">&larr; Back to Session History</Link>
      </Button>

      {status === "loading" && (
        <Skeleton
          shape="block"
          className="h-72 w-full"
          aria-busy="true"
          aria-label="Loading session"
        />
      )}

      {status === "error" && (
        <Alert
          tone="danger"
          actions={
            <>
              <Button variant="danger" size="sm" onClick={retry}>
                Retry
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link href="/practice/speaking/history">Back to History</Link>
              </Button>
            </>
          }
        >
          {error ?? "This session could not be found."}
        </Alert>
      )}

      {status === "success" && session && (
        <div className="space-y-6">
          <Card>
            <Badge tone="brand" pill>
              {session.question_type}
            </Badge>
            <Heading as="h1" size="lg" className="mt-3">
              {session.question_prompt}
            </Heading>
            <Text size="xs" tone="subtle" className="mt-1">
              {formatSessionDateTime(session.created_at)}
            </Text>

            <div className="mt-4">
              <ShareButton sessionId={session.id} />
            </div>
          </Card>

          <EvaluationBreakdown
            overallBand={session.overall_band}
            criteria={extractCriteriaScores(session.evaluation)}
            enableAskDalil
            subjectId={session.id}
            className="max-w-none rounded-card border border-brand-border bg-surface p-6 shadow-e1"
          />

          {session.transcript && (
            <Card>
              <button
                type="button"
                onClick={() => setTranscriptOpen((open) => !open)}
                aria-expanded={transcriptOpen}
                className="flex w-full items-center justify-between text-left text-sm font-bold tracking-wide text-fg-subtle uppercase"
              >
                Transcript
                <span aria-hidden="true">{transcriptOpen ? "−" : "+"}</span>
              </button>
              {transcriptOpen && (
                <Text size="sm" tone="muted" className="mt-3 leading-relaxed whitespace-pre-wrap">
                  {session.transcript}
                </Text>
              )}
            </Card>
          )}
        </div>
      )}
    </PageContainer>
  );
}

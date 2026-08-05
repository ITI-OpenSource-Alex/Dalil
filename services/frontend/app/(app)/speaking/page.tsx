"use client";

import Link from "next/link";
import { ArrowRight, History, Mic } from "lucide-react";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import { formatBand } from "@/lib/ielts";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Heading,
  Icon,
  PageContainer,
  Skeleton,
  Text,
} from "@/components/ui";

/**
 * The Speaking section's landing page.
 *
 * "Speaking History" used to sit at the top level of the sidebar, as a peer of
 * Chat and IELTS -- a *history view* of one practice mode at the same altitude
 * as the product's primary sections, with no page representing Speaking
 * itself. This is that page: it points at the one place a session can actually
 * be started (the mic in Chat), shows where the user currently stands, and
 * makes History the sub-page it always was.
 */
export default function SpeakingPage() {
  const { sessions, status, error, retry } = useSessionHistory();

  const scored = sessions.filter(
    (s): s is typeof s & { overall_band: number } => s.overall_band !== null,
  );
  const latest = scored[0] ?? null;
  const best = scored.length
    ? scored.reduce((a, b) => (b.overall_band > a.overall_band ? b : a))
    : null;

  return (
    <PageContainer size="lg">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Speaking Practice
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          IELTS Speaking
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Answer a Part 2 prompt out loud and get scored on fluency, lexical
          range, grammar and pronunciation.
        </Text>
      </div>

      <Card className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
            <Icon icon={Mic} size="md" />
          </span>
          <div>
            <Text className="font-semibold">Start a practice session</Text>
            <Text size="sm" tone="muted" className="mt-0.5">
              Sessions run in Chat, where the microphone and live transcript
              live.
            </Text>
          </div>
        </div>
        <Button trailingIcon={ArrowRight} asChild className="shrink-0">
          <Link href="/chat">Open Chat</Link>
        </Button>
      </Card>

      {status === "loading" && (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
          aria-busy="true"
          aria-label="Loading your speaking results"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full" shape="block" />
          ))}
        </div>
      )}

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
          icon={Mic}
          title="No sessions yet"
          description="Your first take will appear here with a full band breakdown."
          actions={
            <Button asChild>
              <Link href="/chat">Start practising</Link>
            </Button>
          }
        />
      )}

      {status === "success" && sessions.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Stat label="Sessions" value={String(sessions.length)} />
            <Stat
              label="Latest band"
              // "Not scored" rather than 0.0: fewer than three completed
              // criteria yields null, and 0.0 is a real IELTS band.
              value={latest ? formatBand(latest.overall_band) : "Not scored"}
            />
            <Stat
              label="Best band"
              value={best ? formatBand(best.overall_band) : "Not scored"}
            />
          </div>

          <div className="mt-6">
            <Button variant="secondary" leadingIcon={History} asChild>
              <Link href="/speaking/history">
                View full history and trend
              </Link>
            </Button>
          </div>
        </>
      )}
    </PageContainer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <Text size="sm" tone="subtle">
        {label}
      </Text>
      <p className="mt-1 text-2xl font-bold text-fg tabular-nums">{value}</p>
    </Card>
  );
}

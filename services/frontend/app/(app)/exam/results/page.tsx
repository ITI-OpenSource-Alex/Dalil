"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { SkillArea } from "@/app/types/exam";
import { getResult, getSession, getWritingResult } from "@/lib/exam-api";
import Skeleton from "@/components/ui/skeleton";
import type { ExamResultResponse, WritingResultResponse } from "@/lib/exam-api";
import CombinedWritingResults from "@/components/writing/CombinedWritingResults";
import {
  loadReadingResult,
  type StoredReadingResult,
} from "@/lib/reading-result-storage";
import {
  loadListeningResult,
  type StoredListeningResult,
} from "@/lib/listening-result-storage";
import ReadingResultsView from "@/components/reading/results/ReadingResultsView";
import { READING_UI_TYPE_LABELS } from "@/lib/reading-results";
import { Badge, Button, Card, Heading, PageContainer, Text } from "@/components/ui";

// useSearchParams() opts the page into client-side rendering during
// prerendering, which Next.js requires to be wrapped in a Suspense boundary
// (https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout) —
// otherwise `next build`'s static export of this route fails.
export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <PageContainer size="xl">
          <div className="space-y-6">
            <Skeleton className="h-32 w-full rounded-panel" />
            <Skeleton className="h-24 w-full rounded-card" />
          </div>
        </PageContainer>
      }
    >
      <ResultsPageContent />
    </Suspense>
  );
}

function ResultsPageContent() {
  const searchParams = useSearchParams();
  const skill = (searchParams.get("skill") || "Reading") as SkillArea;
  const [mounted, setMounted] = useState(false);
  const sessionId = searchParams.get("session") || "";
  const [result, setResult] = useState<ExamResultResponse | null>(null);
  const [readingResult, setReadingResult] =
    useState<StoredReadingResult | null>(null);
  const [listeningResult, setListeningResult] =
    useState<StoredListeningResult | null>(null);
  const [writingResult, setWritingResult] =
    useState<WritingResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // doc 11: bumped by handleRetry to re-run the load effect below without
  // duplicating its fetch logic in a second function.
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleRetry = () => {
    setError(null);
    setLoading(true);
    setRetryCount((n) => n + 1);
  };

  useEffect(() => {
    if (!sessionId) return;

    // Reading has no GET-result endpoint on the backend (see
    // lib/reading-result-storage.ts) — its full per-question breakdown was
    // captured client-side at submit time and only needs to be read back
    // out of sessionStorage, synchronously, no network round trip.
    if (skill === "Reading") {
      const stored = loadReadingResult(sessionId);
      setReadingResult(stored);
      setLoading(false);

      if (!stored) {
        setError("No Reading result found for this session.");
        return;
      }

      sessionStorage.removeItem("active_exam_session");

      return;
    }

    // Listening is stored and read back exactly like Reading, and for the same
    // reason -- the exam service has no GET-result endpoint for it either, so
    // the submit response captured client-side is the only copy of the
    // per-question breakdown. See lib/listening-result-storage.ts.
    if (skill === "Listening") {
      const stored = loadListeningResult(sessionId);
      setListeningResult(stored);
      setLoading(false);

      if (!stored) {
        setError("No Listening result found for this session.");
        return;
      }

      sessionStorage.removeItem("active_exam_session");

      return;
    }

    // Writing does have a GET-result endpoint, but its payload is not
    // ExamResultResponse: the exam service branches to _get_writing_result and
    // returns a weighted `overall_band` plus both task records instead of
    // raw_score/band_score. Reading it through the generic path produced an
    // empty banner and posted `bandScore: undefined` to the profile.
    if (skill === "Writing") {
      (async () => {
        try {
          setLoading(true);
          const writing = await getWritingResult(sessionId);
          setWritingResult(writing);

          sessionStorage.removeItem("active_exam_session");
        } catch (err) {
          setError(
            err instanceof Error ? err.message : "Failed to load result",
          );
        } finally {
          setLoading(false);
        }
      })();

      return;
    }

    async function loadResult() {
      try {
        setLoading(true);

        const [, resultData] = await Promise.all([
          getSession(sessionId),
          getResult(sessionId),
        ]);

        setResult(resultData);

        sessionStorage.removeItem("active_exam_session");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load result");
      } finally {
        setLoading(false);
      }
    }

    loadResult();
  }, [sessionId, skill, retryCount]);

  // doc 11: previously bare <div>Loading...</div> / <div>{error}</div>
  // with no styling at all -- replaced with the Skeleton component
  // (extended above to support block sizing) approximating the real
  // results layout, and the same styled error/retry card pattern already
  // used on /profile and ChecklistView, rather than a third distinct
  // error style.
  if (loading) {
    return (
      <PageContainer size="xl">
        <div className="space-y-6" aria-busy="true" aria-label="Loading exam results">
          <Skeleton className="h-32 w-full rounded-panel" />
          <Skeleton className="h-24 w-full rounded-card" />
          <Skeleton className="h-40 w-full rounded-card" />
        </div>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer size="xl">
        <Card className="text-center">
          <Text size="sm" tone="danger">
            {error}
          </Text>
          <Button variant="danger" size="sm" className="mt-3" onClick={handleRetry}>
            Retry
          </Button>
        </Card>
      </PageContainer>
    );
  }

  if (skill === "Reading") {
    if (!readingResult) {
      return (
        <PageContainer size="xl">
          <Text tone="muted">No result found.</Text>
        </PageContainer>
      );
    }

    return (
      <PageContainer size="xl">
        <div
          className={`transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <ReadingResultsView
            result={readingResult.result}
            questions={readingResult.questions}
          />
        </div>
      </PageContainer>
    );
  }

  if (skill === "Listening") {
    if (!listeningResult) {
      return (
        <PageContainer size="xl">
          <Text tone="muted">No result found.</Text>
        </PageContainer>
      );
    }

    // ReadingResultsView is deliberately reused rather than duplicated: the
    // two results payloads have the same shape, and the labels that do differ
    // (heading, CTA, per-question "Section N" vs "Passage N", the fourth
    // section) are all props. The test ids are overridden so the Listening
    // e2e specs can target this view without colliding with Reading's.
    return (
      <PageContainer size="xl">
        <div
          className={`transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <ReadingResultsView
            result={listeningResult.result}
            questions={listeningResult.questions}
            title="Listening Results"
            buttonLabel="Practice Listening Again"
            buttonHref="/exam"
            resultTestId="listening-results-view"
            bandScoreTestId="listening-band-score"
            buttonTestId="practice-listening-again-button"
            questionTypeLabels={READING_UI_TYPE_LABELS}
            locationLabel="Section"
            sections={[
              { key: "section_1", label: "Section 1" },
              { key: "section_2", label: "Section 2" },
              { key: "section_3", label: "Section 3" },
              { key: "section_4", label: "Section 4" },
            ]}
          />
        </div>
      </PageContainer>
    );
  }

  if (skill === "Writing") {
    if (!writingResult) {
      return (
        <PageContainer size="xl">
          <Text tone="muted">No result found.</Text>
        </PageContainer>
      );
    }

    return (
      <PageContainer size="xl">
        <div
          className={`transition-all duration-700 ease-out ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          <CombinedWritingResults result={writingResult} />
        </div>
      </PageContainer>
    );
  }

  if (!result) {
    return (
      <PageContainer size="xl">
        <Text tone="muted">No result found.</Text>
      </PageContainer>
    );
  }

  // Only the generic result shape reaches here -- Reading and Writing each
  // returned from their own branch above, so no narrowing is needed and
  // section_scores is always present on `result`.
  const sectionScores: [string, number][] = Object.entries(
    result.section_scores ?? {},
  ).filter(
    (entry): entry is [string, number] =>
      typeof entry[1] === "number" && Number.isFinite(entry[1]),
  );
  const weakestSection = [...sectionScores].sort(([, a], [, b]) => a - b)[0];

  return (
    <PageContainer size="xl">
      <div
        className={`transition-all duration-700 ease-out ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        {/* Result Banner */}
        <Card className="mb-8 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
          <div className="space-y-1">
            <Badge tone="brand" pill>
              Official Simulation Result
            </Badge>
            <Heading as="h1" size="xl" className="mt-2">
              {skill} Analytics
            </Heading>
          </div>
          <div className="shrink-0 rounded-card border border-border bg-canvas-subtle px-6 py-3 text-center">
            <Text size="xs" tone="subtle" weight="semibold" className="tracking-widest uppercase">
              Overall band
            </Text>
            <p className="font-serif text-4xl font-bold text-brand-fg">
              {result.band_score ?? "—"}
            </p>
            {result.band_score === null && (
              <Text size="xs" tone="muted">
                Not enough criteria completed to score
              </Text>
            )}
            <Text size="sm" tone="muted">
              Raw Score: {result.raw_score}
            </Text>
          </div>
        </Card>

        {/* Generic (non-Writing) result rendering, from the authenticated
            progress work on dev. Writing takes the branch above because
            its payload carries no section_scores at all. */}
        <section className="mb-8">
          <Text size="sm" tone="subtle" weight="semibold" className="mb-4 tracking-wide uppercase">
            Diagnostic Feed
          </Text>

          {sectionScores.length ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {sectionScores.map(([section, score]) => (
                <Card key={section} padding="sm">
                  <Heading as="h3" size="sm" className="capitalize">
                    {section.replaceAll("_", " ")}
                  </Heading>
                  <Text size="xs" tone="muted" className="mt-2 leading-relaxed">
                    Score: {score}
                  </Text>
                </Card>
              ))}
            </div>
          ) : (
            <Text size="xs" tone="muted">
              Detailed section feedback is not available for this result.
            </Text>
          )}
        </section>

        {/* Action Engine Block */}
        <Card>
          <Heading as="h2" size="md" className="mb-3">
            Targeted Action Plan
          </Heading>
          <ul className="list-disc space-y-2 pl-4 text-xs leading-relaxed text-fg-muted">
            {weakestSection ? (
              <li>
                <strong>Focus on {weakestSection[0].replaceAll("_", " ")}:</strong>{" "}
                it is the lowest reported section score ({weakestSection[1]}).
              </li>
            ) : (
              <li>Complete another scored exam to receive a data-backed action plan.</li>
            )}
          </ul>
          <div className="mt-6 border-t border-border pt-4">
            <Button size="sm" asChild>
              <Link href="/exam">Return to Skills Workspace</Link>
            </Button>
          </div>
        </Card>
      </div>
    </PageContainer>
  );
}

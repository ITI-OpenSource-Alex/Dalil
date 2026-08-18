"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileText,
  Quote,
  Sparkles,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  PageContainer,
  Progress,
  Spinner,
  Text,
  Textarea,
} from "@/components/ui";
import { reviewMotivationLetter } from "@/lib/motivation-api";
import type {
  MotivationLetterCriterion,
  MotivationLetterReview,
} from "@/app/types/checklist";

const MIN_WORDS = 100;
const TYPICAL_MIN = 500;
const TYPICAL_MAX = 800;
const DRAFT_KEY_PREFIX = "goa:motivation-letter:";

const CRITERIA_ORDER = [
  "programme_fit",
  "motivation_clarity",
  "evidence_of_qualification",
  "structure_and_flow",
  "language_quality",
] as const;

const CRITERION_LABELS: Record<string, string> = {
  programme_fit: "Programme fit",
  motivation_clarity: "Motivation clarity",
  evidence_of_qualification: "Evidence of qualification",
  structure_and_flow: "Structure and flow",
  language_quality: "Language quality",
};

const CRITERION_BLURBS: Record<string, string> = {
  programme_fit: "Does this read as written for this programme, or for any programme?",
  motivation_clarity: "Is the reason for applying specific and credible?",
  evidence_of_qualification: "Are claims backed by concrete experience?",
  structure_and_flow: "Opening, progression, paragraphing, close.",
  language_quality: "Register, accuracy, concision, academic tone.",
};

function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

/** 1–5 as a filled pip row — readable at a glance without parsing a number. */
function ScorePips({ score, size = "md" }: { score: number; size?: "md" | "lg" }) {
  const bar = size === "lg" ? "h-2.5 w-9" : "h-2 w-7";
  return (
    <span className="flex items-center gap-1" aria-label={`${score} out of 5`}>
      {[1, 2, 3, 4, 5].map((pip) => (
        <span
          key={pip}
          className={`${bar} rounded-full ${
            pip <= Math.round(score) ? "bg-brand" : "bg-canvas-inset"
          }`}
        />
      ))}
    </span>
  );
}

/** A score, or an explicit abstention. A null score is never rendered as 0. */
function CriterionScore({ criterion }: { criterion: MotivationLetterCriterion }) {
  if (criterion.score === null) {
    return (
      <Badge tone="neutral" variant="subtle">
        {criterion.status === "error" ? "Not assessed" : "Insufficient evidence"}
      </Badge>
    );
  }
  return (
    <div className="flex shrink-0 items-center gap-3">
      <ScorePips score={criterion.score} />
      <span className="text-2xl font-semibold tabular-nums leading-none text-brand-fg">
        {criterion.score}
        <span className="text-base font-normal text-fg-subtle">/5</span>
      </span>
    </div>
  );
}

export default function MotivationLetterPage() {
  const params = useParams<{ programId: string }>();
  const programId = params?.programId ?? "";
  const draftKey = `${DRAFT_KEY_PREFIX}${programId}`;

  const [content, setContent] = useState("");
  const [programName, setProgramName] = useState<string | null>(null);
  const [review, setReview] = useState<MotivationLetterReview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore the draft first: a review takes tens of seconds, and a reload
  // mid-flight must not cost the student their letter.
  useEffect(() => {
    if (typeof window === "undefined" || !programId) return;
    const saved = window.localStorage.getItem(draftKey);
    if (saved) setContent(saved);
  }, [draftKey, programId]);

  useEffect(() => {
    if (typeof window === "undefined" || !programId) return;
    window.localStorage.setItem(draftKey, content);
  }, [content, draftKey, programId]);

  // The programme name comes from the review's programmeSnapshot: the checklist
  // response carries only the programme id, and rendering that put a raw UUID in
  // the heading -- the anonymous-checklist defect
  // reports/frontend-e2e-ux-audit-2026-08-09.md flagged. Before a review exists we
  // say nothing rather than showing an id no student can read.
  useEffect(() => {
    const name = review?.programmeSnapshot?.name;
    if (typeof name === "string" && name) setProgramName(name);
  }, [review]);

  const words = countWords(content);
  const canSubmit = words >= MIN_WORDS && !submitting;

  const submit = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      setReview(await reviewMotivationLetter({ content, programId }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed");
    } finally {
      setSubmitting(false);
    }
  }, [content, programId]);

  const orderedCriteria = useMemo(() => {
    if (!review) return [];
    const byName = new Map(review.criteria.map((c) => [c.criterion, c]));
    return CRITERIA_ORDER.map((name) => byName.get(name)).filter(
      (c): c is MotivationLetterCriterion => Boolean(c),
    );
  }, [review]);

  const unaddressed =
    orderedCriteria.find((c) => c.criterion === "programme_fit")
      ?.unaddressed_requirements ?? [];
  const scoredCount = orderedCriteria.filter((c) => c.score !== null).length;

  return (
    <PageContainer size="lg" className="space-y-6 py-6">
      <div>
        <Link
          href={`/checklist/${encodeURIComponent(programId)}`}
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-brand-fg"
        >
          <ArrowLeft size={15} aria-hidden="true" />
          Back to checklist
        </Link>

        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <Heading size="lg">Motivation letter review</Heading>
            <Text tone="muted" className="mt-1">
              {programName
                ? `Checked against ${programName} and its published requirements.`
                : "Checked against this programme and its published requirements."}
            </Text>
          </div>
          <Badge tone="brand" variant="subtle">
            <Sparkles size={12} className="mr-1 inline" aria-hidden="true" />
            5 criteria
          </Badge>
        </div>
      </div>

      <Card variant="raised" className="space-y-3">
        <div className="flex items-center gap-2">
          <FileText size={17} className="text-brand-fg" aria-hidden="true" />
          <Heading size="sm">Your letter</Heading>
        </div>

        <Textarea
          id="letter"
          data-testid="motivation-letter-input"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={24}
          disabled={submitting}
          placeholder="Paste or write your motivation letter here…"
          className="min-h-[32rem] resize-y text-base leading-relaxed"
        />

        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-medium tabular-nums text-brand-fg">
              {words} words
            </span>
            {words < MIN_WORDS ? (
              <span className="text-fg-subtle">
                · {MIN_WORDS - words} more needed to review
              </span>
            ) : words < TYPICAL_MIN ? (
              <span className="text-fg-subtle">
                · shorter than the typical {TYPICAL_MIN}–{TYPICAL_MAX}
              </span>
            ) : words > TYPICAL_MAX ? (
              <span className="text-fg-subtle">
                · longer than the typical {TYPICAL_MIN}–{TYPICAL_MAX}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-fg-subtle">
                <CheckCircle2 size={13} aria-hidden="true" />
                typical length
              </span>
            )}
          </div>
          <Text size="xs" tone="subtle">
            Drafts save automatically
          </Text>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <Button
            data-testid="motivation-letter-submit"
            onClick={submit}
            disabled={!canSubmit}
            size="lg"
          >
            {submitting ? "Reviewing…" : review ? "Review again" : "Review my letter"}
          </Button>
          {submitting && (
            <span className="inline-flex items-center gap-2 text-sm text-fg-muted">
              <Spinner size="sm" />
              Assessing five criteria — usually under a minute
            </span>
          )}
        </div>

        {error && (
          <Alert tone="danger" data-testid="motivation-letter-error">
            {error}
          </Alert>
        )}
      </Card>

      {review && (
        <section data-testid="motivation-letter-review" className="space-y-5">
          <Card variant="raised">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <Heading size="md">Overall</Heading>
                <Text size="sm" tone="subtle" className="mt-0.5">
                  {scoredCount} of {orderedCriteria.length} criteria scored
                </Text>
              </div>
              {review.overallScore !== null ? (
                <div className="flex items-center gap-4">
                  <ScorePips score={review.overallScore} size="lg" />
                  <span className="text-5xl font-bold tabular-nums leading-none text-brand-fg">
                    {review.overallScore}
                    <span className="text-2xl font-normal text-fg-subtle">/5</span>
                  </span>
                </div>
              ) : (
                <Badge tone="warning" variant="subtle">
                  Partial — too few criteria scored for an overall
                </Badge>
              )}
            </div>
            {review.overallScore !== null && (
              <Progress
                className="mt-4"
                label="Overall score"
                showValue={false}
                value={review.overallScore}
                max={5}
                valueText={`${review.overallScore} out of 5`}
              />
            )}
          </Card>

          {/* The headline, above the scores on purpose: it is the one output a
              general-purpose assistant cannot produce, because it comes from this
              programme's scraped requirements. */}
          {unaddressed.length > 0 && (
            <Card
              variant="raised"
              data-testid="unaddressed-requirements"
              className="border-l-4 border-l-warning"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle
                  size={22}
                  className="mt-0.5 shrink-0 text-warning"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <Heading size="md">
                    Requirements your letter does not address
                  </Heading>
                  <ul className="mt-3 space-y-2.5">
                    {unaddressed.map((requirement) => (
                      <li
                        key={requirement}
                        className="flex gap-2.5 text-base leading-relaxed text-brand-fg"
                      >
                        <span aria-hidden="true" className="text-warning">
                          •
                        </span>
                        <span>{requirement}</span>
                      </li>
                    ))}
                  </ul>
                  <Text size="sm" tone="subtle" className="mt-3">
                    Drawn from the requirements scraped for this programme — only as
                    complete as that data.
                  </Text>
                </div>
              </div>
            </Card>
          )}

          <div className="space-y-4">
            {orderedCriteria.map((criterion) => (
              <Card
                key={criterion.criterion}
                variant="raised"
                data-testid={`criterion-${criterion.criterion}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-3">
                  <div className="min-w-0">
                    <Heading size="md">
                      {CRITERION_LABELS[criterion.criterion] ?? criterion.criterion}
                    </Heading>
                    <Text size="sm" tone="subtle" className="mt-1">
                      {CRITERION_BLURBS[criterion.criterion]}
                    </Text>
                  </div>
                  <CriterionScore criterion={criterion} />
                </div>

                {criterion.strengths.length > 0 && (
                  <div className="mt-4">
                    <Text
                      size="xs"
                      tone="subtle"
                      className="font-semibold uppercase tracking-wide"
                    >
                      What works
                    </Text>
                    <ul className="mt-2 space-y-2">
                      {criterion.strengths.map((strength) => (
                        <li
                          key={strength}
                          className="flex gap-2.5 text-base leading-relaxed text-fg-muted"
                        >
                          <CheckCircle2
                            size={17}
                            className="mt-1 shrink-0 text-success"
                            aria-hidden="true"
                          />
                          <span>{strength}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {criterion.issues.length > 0 && (
                  <div className="mt-5">
                    <Text
                      size="xs"
                      tone="subtle"
                      className="font-semibold uppercase tracking-wide"
                    >
                      What to fix
                    </Text>
                    <div className="mt-2 space-y-3">
                      {criterion.issues.map((issue, index) => (
                        <div
                          key={`${criterion.criterion}-${index}`}
                          className="rounded-xl border border-border bg-canvas-subtle p-4"
                        >
                          {issue.quote && (
                            <div className="flex gap-2">
                              <Quote
                                size={15}
                                className="mt-1 shrink-0 text-fg-subtle"
                                aria-hidden="true"
                              />
                              <blockquote className="text-base italic leading-relaxed text-fg-muted">
                                {issue.quote}
                              </blockquote>
                            </div>
                          )}
                          <p className="mt-3 text-base leading-relaxed text-brand-fg">
                            {issue.why}
                          </p>
                          {issue.suggestion && (
                            <p className="mt-2.5 rounded-lg bg-brand-subtle p-3 text-base leading-relaxed text-brand-fg">
                              <span className="font-semibold">Try: </span>
                              {issue.suggestion}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            ))}
          </div>

          <Text size="sm" tone="subtle">
            Guidance only. Scores are out of 5 against admissions criteria — they are
            not IELTS bands, not an official assessment, and not a prediction of
            admission.
          </Text>
        </section>
      )}
    </PageContainer>
  );
}

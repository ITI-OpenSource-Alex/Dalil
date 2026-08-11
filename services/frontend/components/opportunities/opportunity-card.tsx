"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Calendar,
  ExternalLink,
  GraduationCap,
  ListChecks,
  MapPin,
} from "lucide-react";
import { cn } from "@/lib/cn";
import {
  MATCH_TONE_LABEL,
  blockedReason,
  daysUntil,
  formatDeadline,
  matchTone,
  type MatchTone,
  type MatchedProgram,
} from "@/lib/opportunities-api";
import { Badge, Button, Card, Icon, Text } from "@/components/ui";
import { ExplainWithDalilButton } from "@/components/chat/explain-with-dalil-button";
import { compactFacts, fact } from "@/lib/explanation-context";

const TONE_BADGE: Record<
  MatchTone,
  "success" | "warning" | "danger" | "neutral"
> = {
  strong: "success",
  possible: "warning",
  stretch: "danger",
  blocked: "neutral",
  unknown: "neutral",
};

const TONE_BAR: Record<MatchTone, string> = {
  strong: "bg-success",
  possible: "bg-warning",
  stretch: "bg-danger",
  blocked: "bg-fg-subtle",
  unknown: "bg-fg-subtle",
};

export function OpportunityCard({
  program,
  onOpen,
}: {
  program: MatchedProgram;
  onOpen?: (program: MatchedProgram) => void;
}) {
  const tone = matchTone(program);
  const score = Math.round(program.result.score);
  const deadline = formatDeadline(program.deadline);
  const days = daysUntil(program.deadline);
  const reason = blockedReason(program.result.blocked_by);

  // A deadline is only worth flagging while it is both real and imminent.
  // "Closed" is shown for a past one rather than a negative countdown.
  const deadlineUrgency =
    days === null ? null : days < 0 ? "closed" : days <= 30 ? "soon" : null;

  const open = () => onOpen?.(program);

  // Primary region is the activatable control; footer links stay outside so
  // Tab order is open → checklist → Ask GOA (no nested interactive).
  const details = (
    <>
      <div className="flex min-w-0 items-start justify-between gap-3">
        <h3
          data-testid="opportunity-title"
          className="min-w-0 flex-1 truncate text-sm font-bold text-fg"
          title={program.programName}
        >
          {program.programName}
        </h3>
        <Badge tone={TONE_BADGE[tone]} size="sm" pill className="mr-9 shrink-0">
          {tone === "blocked" || tone === "unknown"
            ? MATCH_TONE_LABEL[tone]
            : `${score}% fit`}
        </Badge>
      </div>

      <dl className="flex flex-col gap-1.5 text-sm text-fg-muted">
        <div className="flex min-w-0 items-center gap-2">
          <dt className="sr-only">University</dt>
          <Icon
            icon={GraduationCap}
            size="xs"
            className="shrink-0 text-fg-subtle"
          />
          <dd
            data-testid="opportunity-university"
            className="min-w-0 flex-1 truncate"
            title={program.university}
          >
            {program.university}
          </dd>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <dt className="sr-only">Country</dt>
          <Icon icon={MapPin} size="xs" className="shrink-0 text-fg-subtle" />
          <dd className="min-w-0 flex-1 truncate" title={program.country}>
            {program.country}
          </dd>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <dt className="sr-only">Application deadline</dt>
          <Icon icon={Calendar} size="xs" className="shrink-0 text-fg-subtle" />
          <dd className="flex min-w-0 flex-1 items-center gap-2">
            {/* "No published deadline" rather than "Deadline: null" — RAG
                returns null for undated programmes and the chat card printed
                it verbatim. */}
            <span
              className="min-w-0 flex-1 truncate"
              title={deadline ?? "No published deadline"}
            >
              {deadline ?? "No published deadline"}
            </span>
            {deadlineUrgency === "soon" && (
              <Badge tone="warning" size="sm" pill>
                {days === 0 ? "Closes today" : `${days} days left`}
              </Badge>
            )}
            {deadlineUrgency === "closed" && (
              <Badge tone="neutral" size="sm" pill>
                Closed
              </Badge>
            )}
          </dd>
        </div>
      </dl>

      {reason ? (
        <div className="flex items-start gap-2 rounded-control bg-canvas-subtle p-3">
          <Icon
            icon={AlertTriangle}
            size="xs"
            className="mt-0.5 shrink-0 text-warning-fg"
          />
          <Text size="sm" tone="muted" className="line-clamp-2" title={reason ?? undefined}>
            {reason}
          </Text>
        </div>
      ) : tone === "unknown" ? (
        <Text
          size="sm"
          tone="muted"
          className="line-clamp-2"
          title="This programme has not published enough structured academic criteria for a reliable fit score yet."
        >
          This programme has not published enough structured academic criteria
          for a reliable fit score yet.
        </Text>
      ) : (
        <div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-canvas-inset">
            <div
              className={cn(
                "h-full rounded-full transition-[width]",
                TONE_BAR[tone],
              )}
              style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
            />
          </div>
          <Text
            size="sm"
            tone="subtle"
            className="mt-1.5 truncate"
            title={`${MATCH_TONE_LABEL[tone]} against your profile`}
          >
            {MATCH_TONE_LABEL[tone]} against your profile
          </Text>
          {program.result.score_breakdown?.subject_relevance !== null &&
            program.result.score_breakdown?.subject_relevance !== undefined && (
              <Text
                size="sm"
                className="mt-0.5 truncate font-medium text-fg-muted"
                title={
                  program.result.score_breakdown.subject_relevance >= 0.9
                    ? "Exact intended-field match"
                    : "Related intended field"
                }
              >
                {program.result.score_breakdown.subject_relevance >= 0.9
                  ? "Exact intended-field match"
                  : "Related intended field"}
              </Text>
            )}
          {program.result.requirements_evaluated !== undefined && (
            <Text
              size="sm"
              tone="subtle"
              className="mt-0.5 truncate"
              title={`${program.result.requirements_met ?? 0} of ${program.result.requirements_evaluated} published requirements met`}
            >
              {program.result.requirements_met ?? 0} of{" "}
              {program.result.requirements_evaluated} published requirements met
            </Text>
          )}
          {program.result.score_breakdown?.requirement_headroom_points !==
            null &&
            program.result.score_breakdown?.requirement_headroom_points !==
              undefined && (
              <Text
                size="sm"
                tone="subtle"
                className="mt-0.5 truncate"
                title={`Score: ${Math.round(program.result.score_breakdown.eligibility_points)} eligibility + ${Math.round(program.result.score_breakdown.requirement_headroom_points)} requirement headroom + ${Math.round(program.result.score_breakdown.subject_points ?? 0)} subject fit + ${Math.round(program.result.score_breakdown.destination_points ?? 0)} destination fit`}
              >
                Score:{" "}
                {Math.round(program.result.score_breakdown.eligibility_points)}{" "}
                eligibility +{" "}
                {Math.round(
                  program.result.score_breakdown.requirement_headroom_points,
                )}{" "}
                requirement headroom +{" "}
                {Math.round(program.result.score_breakdown.subject_points ?? 0)}{" "}
                subject fit +{" "}
                {Math.round(
                  program.result.score_breakdown.destination_points ?? 0,
                )}{" "}
                destination fit
              </Text>
            )}
        </div>
      )}
    </>
  );

  return (
    <Card
      variant={onOpen ? "interactive" : "flat"}
      className="relative flex h-full w-full min-w-0 flex-col gap-4 overflow-hidden"
    >
      <ExplainWithDalilButton
        context={{
          kind: "programme_match",
          title: `${program.programName} fit result`,
          subjectId: program.programId,
          summary: `${program.university} · ${program.country}`,
          facts: compactFacts([
            fact("Programme", program.programName, program.sourceUrl),
            fact("University", program.university, program.sourceUrl),
            fact("Country", program.country),
            fact("Fit score", `${score}%`),
            fact("Fit classification", MATCH_TONE_LABEL[tone]),
            fact("Blocking requirement", reason),
            fact("Published requirements met", program.result.requirements_met),
            fact("Published requirements evaluated", program.result.requirements_evaluated),
            fact("Eligibility points", program.result.score_breakdown?.eligibility_points),
            fact("Requirement headroom points", program.result.score_breakdown?.requirement_headroom_points),
            fact("Subject fit points", program.result.score_breakdown?.subject_points),
            fact("Destination fit points", program.result.score_breakdown?.destination_points),
            fact(
              "Application deadline",
              deadline ?? "No published deadline",
              program.sourceUrl,
            ),
          ]),
          limitations:
            tone === "unknown"
              ? ["The programme has not published enough structured criteria for a reliable fit score."]
              : ["The fit score depends on the profile information currently saved in Dalil."],
        }}
        prompt={`Why is ${program.programName} at ${program.university} shown as ${tone === "blocked" || tone === "unknown" ? MATCH_TONE_LABEL[tone] : `${score}% fit`}? Walk through the score and tell me the most important gap or next step.`}
        className="absolute right-4 top-4 z-10"
      />
      {onOpen ? (
        <div
          role="button"
          tabIndex={0}
          className="flex flex-1 flex-col gap-4 rounded-control outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          aria-label={`View details for ${program.programName} at ${program.university}`}
          onClick={open}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              open();
            }
          }}
        >
          {details}
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-4">{details}</div>
      )}

      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        <Button size="sm" leadingIcon={ListChecks} asChild>
          <Link href={`/checklist/${encodeURIComponent(program.programId)}`}>
            Get checklist
          </Link>
        </Button>
        {program.sourceUrl && program.dataSource === "scraped" && (
          <Button size="sm" variant="ghost" trailingIcon={ExternalLink} asChild>
            <a
              href={program.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Source listing
            </a>
          </Button>
        )}
      </div>
    </Card>
  );
}

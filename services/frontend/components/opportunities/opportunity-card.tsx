"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
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

const TONE_BADGE: Record<
  MatchTone,
  "success" | "warning" | "danger" | "neutral"
> = {
  strong: "success",
  possible: "warning",
  stretch: "danger",
  blocked: "neutral",
};

const TONE_BAR: Record<MatchTone, string> = {
  strong: "bg-success",
  possible: "bg-warning",
  stretch: "bg-danger",
  blocked: "bg-fg-subtle",
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

  return (
    <Card
      variant={onOpen ? "interactive" : "flat"}
      className={cn(
        "flex h-full flex-col gap-4",
        onOpen && "cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-brand-muted",
      )}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      aria-label={
        onOpen
          ? `View details for ${program.programName} at ${program.university}`
          : undefined
      }
      onClick={onOpen ? open : undefined}
      onKeyDown={
        onOpen
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
              }
            }
          : undefined
      }
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-sm font-bold text-fg">
          {program.programName}
        </h3>
        <Badge tone={TONE_BADGE[tone]} size="sm" pill className="shrink-0">
          {tone === "blocked" ? MATCH_TONE_LABEL.blocked : `${score}% match`}
        </Badge>
      </div>

      <dl className="flex flex-col gap-1.5 text-sm text-fg-muted">
        <div className="flex items-center gap-2">
          <dt className="sr-only">University</dt>
          <Icon icon={GraduationCap} size="xs" className="shrink-0 text-fg-subtle" />
          <dd className="min-w-0 truncate">{program.university}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="sr-only">Country</dt>
          <Icon icon={MapPin} size="xs" className="shrink-0 text-fg-subtle" />
          <dd>{program.country}</dd>
        </div>
        <div className="flex items-center gap-2">
          <dt className="sr-only">Application deadline</dt>
          <Icon icon={Calendar} size="xs" className="shrink-0 text-fg-subtle" />
          <dd className="flex flex-wrap items-center gap-2">
            {/* "No published deadline" rather than "Deadline: null" — RAG
                returns null for undated programmes and the chat card printed
                it verbatim. */}
            <span>{deadline ?? "No published deadline"}</span>
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
          <Text size="sm" tone="muted">
            {reason}
          </Text>
        </div>
      ) : (
        <div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-canvas-inset">
            <div
              className={cn("h-full rounded-full transition-[width]", TONE_BAR[tone])}
              style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
            />
          </div>
          <Text size="sm" tone="subtle" className="mt-1.5">
            {MATCH_TONE_LABEL[tone]} against your profile
          </Text>
        </div>
      )}

      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        <Button size="sm" leadingIcon={ListChecks} asChild>
          <Link
            href={`/checklist/${encodeURIComponent(program.programId)}`}
            onClick={(event) => event.stopPropagation()}
          >
            Get checklist
          </Link>
        </Button>
        <Button size="sm" variant="ghost" trailingIcon={ArrowRight} asChild>
          <Link
            href={`/chat?ask=${encodeURIComponent(
              `Tell me more about ${program.programName} at ${program.university}.`,
            )}`}
            onClick={(event) => event.stopPropagation()}
          >
            Ask GOA
          </Link>
        </Button>
      </div>
    </Card>
  );
}

"use client";

import Link from "next/link";
import { Activity, Mic, PenSquare } from "lucide-react";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import { useWritingHistory } from "@/app/hooks/useWritingHistory";
import { Badge, Card, EmptyState, Icon, Skeleton, Text } from "@/components/ui";

interface ActivityItem {
  id: string;
  kind: "speaking" | "writing";
  label: string;
  band: number | null;
  date: string;
  href: string;
}

/** Merges the two practice histories (Speaking, Writing) into one recency-sorted
 *  feed. Reuses the same hooks their own history pages use rather than a new
 *  aggregate endpoint -- there isn't one, and both lists are already small. */
export function RecentActivityWidget() {
  const speaking = useSessionHistory();
  const writing = useWritingHistory();

  const stillLoading =
    (speaking.status === "loading" || speaking.status === "idle") &&
    (writing.status === "loading" || writing.status === "idle");

  if (stillLoading) {
    return (
      <Card>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4" lines={3} />
      </Card>
    );
  }

  const items: ActivityItem[] = [
    ...speaking.sessions.map((session) => ({
      id: `speaking-${session.id}`,
      kind: "speaking" as const,
      label: session.question_prompt,
      band: session.overall_band,
      date: session.created_at,
      href: `/practice/speaking/history/${session.id}`,
    })),
    // No per-essay detail page exists yet (Phase D) -- every writing row
    // links to the history list rather than a dead-end detail URL.
    ...writing.essays.map((essay) => ({
      id: `writing-${essay.id}`,
      kind: "writing" as const,
      label: essay.excerpt,
      band: essay.overall_band,
      date: essay.submitted_at,
      href: "/practice/writing/history",
    })),
  ]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 5);

  return (
    <Card>
      <Text size="sm" tone="muted" className="mb-4 font-semibold">
        Recent activity
      </Text>
      {items.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No practice sessions yet"
          description="Speaking and Writing practice will show up here."
          size="sm"
        />
      ) : (
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item.id}>
              <Link
                href={item.href}
                className="-mx-2 flex items-center justify-between gap-3 rounded-control px-2 py-1.5 transition-colors hover:bg-canvas-subtle"
              >
                <span className="flex min-w-0 items-center gap-2.5">
                  <Icon
                    icon={item.kind === "speaking" ? Mic : PenSquare}
                    size="sm"
                    className="shrink-0 text-fg-subtle"
                  />
                  <Text size="sm" truncate className="min-w-0">
                    {item.label}
                  </Text>
                </span>
                <Badge tone="neutral" size="sm">
                  {item.band != null ? item.band.toFixed(1) : "—"}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, AudioLines, PenSquare } from "lucide-react";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import { useWritingHistory } from "@/app/hooks/useWritingHistory";
import { Button, Card, Icon, Text } from "@/components/ui";

/** Distinct from Quick Actions: this shows *how much* practice a skill has
 *  behind it, not just a link to it -- the two widgets answer different
 *  questions ("where do I go" vs. "how am I doing"). */
export function PracticeShortcutsWidget() {
  const speaking = useSessionHistory();
  const writing = useWritingHistory();

  return (
    <Card>
      <Text size="sm" tone="muted" className="mb-4 font-semibold">
        Practice
      </Text>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <PracticeShortcut
          icon={AudioLines}
          title="Speaking"
          count={speaking.sessions.length}
          href="/practice/speaking"
        />
        <PracticeShortcut
          icon={PenSquare}
          title="Writing"
          count={writing.essays.length}
          href="/practice/writing"
        />
      </div>
    </Card>
  );
}

function PracticeShortcut({
  icon,
  title,
  count,
  href,
}: {
  icon: LucideIcon;
  title: string;
  count: number;
  href: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-card border border-border p-4">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
          <Icon icon={icon} size="sm" />
        </span>
        <div>
          <Text size="sm" weight="semibold">
            {title}
          </Text>
          <Text size="xs" tone="subtle">
            {count} session{count === 1 ? "" : "s"} so far
          </Text>
        </div>
      </div>
      <Button variant="ghost" size="sm" iconOnly asChild aria-label={`Practice ${title}`}>
        <Link href={href}>
          <Icon icon={ArrowRight} size="sm" />
        </Link>
      </Button>
    </div>
  );
}

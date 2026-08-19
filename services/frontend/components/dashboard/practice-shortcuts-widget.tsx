"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, AudioLines, Dumbbell, PenSquare } from "lucide-react";
import { useSessionHistory } from "@/app/hooks/useSessionHistory";
import { useWritingHistory } from "@/app/hooks/useWritingHistory";
import { Card, Icon, Text } from "@/components/ui";

/** Distinct from Quick Actions: this shows *how much* practice a skill has
 *  behind it, not just a link to it -- the two widgets answer different
 *  questions ("where do I go" vs. "how am I doing"). */
export function PracticeShortcutsWidget() {
  const speaking = useSessionHistory();
  const writing = useWritingHistory();

  return (
    <Card data-testid="dashboard-practice">
      <div className="mb-4 flex items-center gap-2">
        <Icon icon={Dumbbell} size="sm" className="text-brand-fg" />
        <Text className="font-semibold">Practice</Text>
      </div>
      <ul className="space-y-2">
        <li>
          <PracticeShortcut
            icon={AudioLines}
            title="Speaking"
            count={speaking.sessions.length}
            href="/practice/speaking"
          />
        </li>
        <li>
          <PracticeShortcut
            icon={PenSquare}
            title="Writing"
            count={writing.essays.length}
            href="/practice/writing"
          />
        </li>
      </ul>
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
    <Link
      href={href}
      className="group flex items-center gap-3 rounded-lg border border-border bg-surface p-3 transition-colors hover:border-brand-border hover:bg-brand-subtle"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
        <Icon icon={icon} size="sm" />
      </span>
      <div className="min-w-0 flex-1">
        <Text as="span" size="sm" weight="semibold" className="block truncate">
          {title}
        </Text>
        <Text as="span" size="xs" tone="subtle" className="block truncate">
          {count} session{count === 1 ? "" : "s"} so far
        </Text>
      </div>
      <Icon
        icon={ArrowRight}
        size="sm"
        className="shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 group-hover:text-brand-fg"
      />
    </Link>
  );
}

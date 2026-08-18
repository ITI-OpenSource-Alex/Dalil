"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  FileText,
  GraduationCap,
  ListChecks,
  PenSquare,
  Target,
} from "lucide-react";
import { Card, Icon, Text } from "@/components/ui";

const ACTIONS: { label: string; href: string; icon: LucideIcon }[] = [
  { label: "Take IELTS Exam", href: "/exam", icon: GraduationCap },
  { label: "Speaking Practice", href: "/practice/speaking", icon: AudioLines },
  { label: "Writing Practice", href: "/practice/writing", icon: PenSquare },
  { label: "Manage CV", href: "/profile?tab=cv", icon: FileText },
  { label: "Opportunities", href: "/opportunities", icon: Target },
  { label: "Checklists", href: "/checklists", icon: ListChecks },
];

/** One tap into each major section -- static, so unlike the other widgets it
 *  needs no fetch of its own and never has an empty or loading state. */
export function QuickActionsWidget() {
  return (
    <Card>
      <Text size="sm" tone="muted" className="mb-4 font-semibold">
        Quick actions
      </Text>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {ACTIONS.map((action) => (
          <Link
            key={action.href}
            href={action.href}
            className="flex flex-col items-center gap-2 rounded-card border border-border bg-surface p-4 text-center transition-colors hover:border-brand-border hover:bg-brand-subtle"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
              <Icon icon={action.icon} size="sm" />
            </span>
            <Text size="sm" weight="medium">
              {action.label}
            </Text>
          </Link>
        ))}
      </div>
    </Card>
  );
}

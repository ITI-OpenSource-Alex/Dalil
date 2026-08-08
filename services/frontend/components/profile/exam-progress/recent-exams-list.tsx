import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { BookOpen, Headphones, Mic, PenLine } from "lucide-react";
import type { ExamHistoryItem } from "@/lib/exam-api";
import { formatBand } from "@/lib/ielts";
import { formatSessionDate } from "@/lib/speaking-format";
import { Badge, Heading, Icon, Text } from "@/components/ui";

const SKILL_ICONS: Record<string, LucideIcon> = {
  reading: BookOpen,
  listening: Headphones,
  speaking: Mic,
  writing: PenLine,
};

function toPascalSkill(skill: string): string {
  const s = skill.toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function examTypeLabel(examType: string): "Academic" | "General" {
  return examType.toLowerCase() === "general" ? "General" : "Academic";
}

function skillIcon(skill: string): LucideIcon {
  return SKILL_ICONS[skill.toLowerCase()] ?? BookOpen;
}

interface RecentExamsListProps {
  items: ExamHistoryItem[];
}

export function RecentExamsList({ items }: RecentExamsListProps) {
  if (items.length === 0) return null;

  return (
    <section className="space-y-3">
      <Heading as="h3" size="xs" className="text-fg-muted">
        Recent exams
      </Heading>
      <ul className="space-y-3">
        {items.map((item) => {
          const SkillIcon = skillIcon(item.skill);
          const skill = toPascalSkill(item.skill);
          const typeLabel = examTypeLabel(item.examType);
          const href = `/exam/results?session=${item.sessionId}&skill=${skill}`;

          return (
            <li
              key={item.sessionId}
              className="flex flex-col gap-3 rounded-card border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
                  <Icon icon={SkillIcon} size="sm" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-fg">{skill}</p>
                    <Badge tone="neutral" size="sm" pill>
                      {typeLabel}
                    </Badge>
                  </div>
                  <Text size="sm" tone="muted" className="mt-0.5">
                    Band {formatBand(item.bandScore)} ·{" "}
                    {formatSessionDate(item.date)}
                  </Text>
                </div>
              </div>
              <Link
                href={href}
                className="shrink-0 text-sm font-medium text-brand-fg hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
              >
                View Results
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

import Link from "next/link";
import type { WeakAreas } from "@/lib/exam-api";
import { Alert, Button, Heading, Text } from "@/components/ui";

const SKILLS = ["reading", "listening", "speaking", "writing"] as const;

const SKILL_LABELS: Record<(typeof SKILLS)[number], string> = {
  reading: "Reading",
  listening: "Listening",
  speaking: "Speaking",
  writing: "Writing",
};

interface WeakAreasPanelProps {
  weakAreas: WeakAreas;
  error: string | null;
  onRetry?: () => void;
}

function skillLabel(skill: string): string {
  const key = skill.toLowerCase() as (typeof SKILLS)[number];
  return SKILL_LABELS[key] ?? skill.charAt(0).toUpperCase() + skill.slice(1);
}

function weakAreaEntries(
  weakAreas: WeakAreas,
): { skill: string; section: string }[] {
  // API returns lowercase skill keys; the TS alias historically used SkillArea.
  const record = weakAreas as Partial<Record<string, string>>;
  const seen = new Set<string>();
  const entries: { skill: string; section: string }[] = [];

  for (const skill of SKILLS) {
    const section =
      record[skill] ??
      record[skill.charAt(0).toUpperCase() + skill.slice(1)];
    if (typeof section !== "string" || section.length === 0) continue;
    seen.add(skill);
    entries.push({ skill, section });
  }

  for (const [skill, section] of Object.entries(record)) {
    if (seen.has(skill.toLowerCase())) continue;
    if (typeof section !== "string" || section.length === 0) continue;
    entries.push({ skill, section });
  }

  return entries;
}

export function WeakAreasPanel({
  weakAreas,
  error,
  onRetry,
}: WeakAreasPanelProps) {
  if (error) {
    return (
      <Alert
        tone="warning"
        title="Weak areas unavailable"
        actions={
          onRetry ? (
            <Button size="sm" variant="secondary" onClick={onRetry}>
              Retry
            </Button>
          ) : undefined
        }
      >
        We couldn&apos;t load your weak areas right now. Charts and recent exams
        are still available.
      </Alert>
    );
  }

  const entries = weakAreaEntries(weakAreas);
  if (entries.length === 0) return null;

  return (
    <section className="space-y-3">
      <Heading as="h3" size="xs" className="text-fg-muted">
        Weak areas
      </Heading>
      <ul className="space-y-3">
        {entries.map(({ skill, section }) => (
          <li
            key={skill}
            className="flex flex-col gap-3 rounded-card border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <p className="text-sm font-semibold text-fg">{skillLabel(skill)}</p>
              <Text size="sm" tone="muted" className="mt-0.5">
                {section}
              </Text>
            </div>
            <Button asChild size="sm" className="shrink-0">
              <Link href="/exam">Practise Now</Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

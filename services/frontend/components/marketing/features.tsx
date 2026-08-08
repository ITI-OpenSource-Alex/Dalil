import {
  Check,
  FileText,
  GraduationCap,
  ListChecks,
  Target,
  type LucideIcon,
} from "lucide-react";
import { Badge, Heading, Icon, Text } from "@/components/ui";
import { cn } from "@/lib/cn";
import { Container, Section, SectionHeader } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * A bento rather than three equal cards.
 *
 * Equal cards force every feature to be equally important, which is
 * false: matching is the product, and IELTS prep is what people pay for.
 * The asymmetric grid says that without a word of copy, and it gives the
 * two lead features room for a visual.
 * ------------------------------------------------------------------ */

function FeatureCard({
  icon,
  title,
  description,
  className,
  children,
  delay = 0,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  className?: string;
  children?: React.ReactNode;
  delay?: number;
}) {
  return (
    <Reveal
      as="article"
      delay={delay}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-card border border-border bg-surface p-7",
        "transition-[border-color,box-shadow] duration-200 ease-out hover:border-border-strong hover:shadow-e1",
        className,
      )}
    >
      <span className="flex h-11 w-11 items-center justify-center rounded-control bg-brand-muted text-brand-fg">
        <Icon icon={icon} size="md" />
      </span>

      <Heading as="h3" size="md" className="mt-5">
        {title}
      </Heading>

      <Text size="sm" tone="muted" className="mt-2">
        {description}
      </Text>

      {children}
    </Reveal>
  );
}

/** Ranked-match visual for the matching card. */
function MatchVisual() {
  const rows = [
    { name: "TU Munich", score: 92 },
    { name: "TU Delft", score: 88 },
    { name: "KTH Stockholm", score: 84 },
  ];

  return (
    <div className="mt-7 flex flex-col gap-2" aria-hidden="true">
      {rows.map((row) => (
        <div
          key={row.name}
          className="flex items-center gap-3 rounded-control border border-border bg-canvas px-3 py-2.5"
        >
          <span className="flex-1 truncate text-sm font-medium text-fg">
            {row.name}
          </span>
          <span className="h-1.5 w-20 overflow-hidden rounded-full bg-canvas-inset">
            <span
              className="block h-full rounded-full bg-brand"
              style={{ width: `${row.score}%` }}
            />
          </span>
          <span className="w-9 text-right text-sm font-semibold tabular-nums text-brand-fg">
            {row.score}%
          </span>
        </div>
      ))}
    </div>
  );
}

/** Phase-grouped checklist visual. */
function ChecklistVisual() {
  const items = [
    { label: "Certified degree transcript", done: true },
    { label: "IELTS 6.5 overall", done: true },
    { label: "Motivation letter", done: false },
    { label: "Blocked account — €11,904", done: false },
  ];

  return (
    <div className="mt-7 flex flex-col gap-2" aria-hidden="true">
      <div className="flex items-center gap-2">
        <Badge tone="brand" size="sm">
          Documents
        </Badge>
        <span className="h-px flex-1 bg-border" />
        <span className="text-xs font-medium tabular-nums text-fg-subtle">
          2 / 4
        </span>
      </div>

      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-2.5 rounded-control border border-border bg-canvas px-3 py-2"
        >
          <span
            className={cn(
              "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border",
              item.done
                ? "border-brand bg-brand text-fg-on-brand"
                : "border-border-strong bg-surface",
            )}
          >
            {item.done && <Icon icon={Check} size="xs" className="h-3 w-3" />}
          </span>
          <span
            className={cn(
              "truncate text-sm",
              item.done ? "text-fg-subtle line-through" : "text-fg",
            )}
          >
            {item.label}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Band-score visual for the IELTS card. */
function BandVisual() {
  const skills = [
    { skill: "Reading", band: 7.5 },
    { skill: "Writing", band: 6.5 },
    { skill: "Speaking", band: 7.0 },
  ];

  return (
    <div className="mt-auto pt-7" aria-hidden="true">
      <div className="rounded-control border border-border bg-canvas p-4">
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-fg-subtle">
            Overall band
          </span>
          <span className="font-serif text-2xl font-semibold text-brand-fg">
            7.0
          </span>
        </div>
        <div className="mt-3 flex flex-col gap-1.5">
          {skills.map((s) => (
            <div key={s.skill} className="flex items-center gap-2">
              <span className="w-16 text-xs text-fg-subtle">{s.skill}</span>
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-canvas-inset">
                <span
                  className="block h-full rounded-full bg-brand"
                  style={{ width: `${(s.band / 9) * 100}%` }}
                />
              </span>
              {/* toFixed(1): IELTS bands are always written to one decimal,
                  and 7.0 was rendering as a bare "7". */}
              <span className="w-6 text-right text-xs font-semibold tabular-nums text-fg">
                {s.band.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** CV feedback visual — annotated lines, the way the review actually reads. */
function CvVisual() {
  const notes = [
    { tone: "danger" as const, label: "Weak verb", line: "Was responsible for a team of 4" },
    { tone: "success" as const, label: "Stronger", line: "Led a team of 4 engineers" },
  ];

  return (
    <div className="mt-auto pt-7" aria-hidden="true">
      <div className="flex flex-col gap-2">
        {notes.map((note) => (
          <div
            key={note.label}
            className={cn(
              "rounded-control border p-3",
              note.tone === "danger"
                ? "border-danger-border bg-danger-subtle"
                : "border-success-border bg-success-subtle",
            )}
          >
            <span
              className={cn(
                "text-[10px] font-semibold tracking-[0.08em] uppercase",
                note.tone === "danger" ? "text-danger-fg" : "text-success-fg",
              )}
            >
              {note.label}
            </span>
            <p className="mt-1 text-sm leading-5 text-fg">{note.line}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Features() {
  return (
    <Section id="features" tone="subtle" labelledBy="features-heading">
      <Container>
        <SectionHeader
          id="features-heading"
          eyebrow="What it does"
          title="Everything the application needs, in one place"
          lead="From your first search to the final upload, Dalil replaces a dozen browser tabs and a spreadsheet you keep forgetting to update."
        />

        <div className="mt-14 grid gap-5 lg:grid-cols-3">
          <FeatureCard
            icon={Target}
            title="Opportunity matching"
            description="Dalil scores your profile against a European catalogue of Master's programmes and scholarships, then ranks the ones you are genuinely competitive for — with the reasoning behind every score."
            className="lg:col-span-2"
          >
            <MatchVisual />
          </FeatureCard>

          <FeatureCard
            icon={GraduationCap}
            title="IELTS preparation"
            description="Full Reading, Listening, Writing and Speaking practice with instant AI band scoring."
            delay={80}
          >
            <BandVisual />
          </FeatureCard>

          <FeatureCard
            icon={FileText}
            title="CV review"
            description="Section-by-section feedback on structure, ATS keywords and the conventions of the country you are applying to."
            delay={160}
          >
            <CvVisual />
          </FeatureCard>

          <FeatureCard
            icon={ListChecks}
            title="Application checklists"
            description="One click turns a matched programme into a personalised, phase-by-phase checklist — documents, deadlines, financial proof and everything after acceptance."
            className="lg:col-span-2"
            delay={240}
          >
            <ChecklistVisual />
          </FeatureCard>
        </div>
      </Container>
    </Section>
  );
}

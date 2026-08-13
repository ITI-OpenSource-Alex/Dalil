import { Gauge, ListChecks, TrendingUp, type LucideIcon } from "lucide-react";
import { Eyebrow, Heading, Icon, Text } from "@/components/ui";
import { Container, Section } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * The page's midpoint anchor, and the first of two dark sections -- the
 * light/dark rhythm is what stops nine stacked white bands reading as a
 * template.
 *
 * This is the slot a testimonial wall would normally occupy. There are no
 * real testimonials for Dalil yet, and inventing quotes, names or outcome
 * statistics would be fabricating evidence on the one page whose entire
 * job is trust. So it argues the position instead, which is both honest
 * and, before a product has users, more persuasive than a wall of
 * invented five-star cards.
 *
 * When real quotes or outcomes exist, they replace the three pillars
 * below without touching the layout.
 * ------------------------------------------------------------------ */

const PILLARS: {
  icon: LucideIcon;
  title: string;
  body: string;
}[] = [
  {
    icon: Gauge,
    title: "Scored, not sorted",
    body: "Every programme comes back with a computed confidence score and the factors behind it — academic fit, language requirement, deadline feasibility — so a shortlist is a decision rather than a guess.",
  },
  {
    icon: ListChecks,
    title: "Nothing discovered late",
    body: "Requirements become a dated, phase-by-phase checklist the moment you pick a programme. Missing documents surface in week one, not the week of the deadline.",
  },
  {
    icon: TrendingUp,
    title: "Progress you can measure",
    body: "Reading, Writing and Speaking come back with band scores and inline feedback after every session, so you can see the gap to your target closing.",
  },
];

export function Proof() {
  return (
    <Section tone="inverse" labelledBy="proof-heading" className="overflow-hidden">
      {/* Texture: the same blueprint grid as the hero, inverted and masked,
          so the two ends of the page rhyme. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-grid-inverse [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,black,transparent)]" />
        <div className="absolute -top-40 left-1/2 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full bg-forest-400/10 blur-3xl" />
      </div>

      <Container>
        <Reveal className="max-w-3xl">
          <Eyebrow tone="inverse-muted">Why Dalil</Eyebrow>

          <Heading
            as="h2"
            id="proof-heading"
            size="2xl"
            tone="inverse"
            className="mt-4"
          >
            Most people apply abroad blind.
          </Heading>

          <Text size="lg" tone="inverse-muted" className="mt-5">
            They shortlist from ranking tables, guess at their own odds, and
            find out about a missing certified translation three days before
            the deadline. Dalil replaces the guesswork with a computed answer at
            every step.
          </Text>
        </Reveal>

        <div className="mt-14 grid gap-px overflow-hidden rounded-card bg-border-inverse sm:grid-cols-3">
          {PILLARS.map((pillar, i) => (
            <Reveal
              key={pillar.title}
              delay={i * 90}
              className="flex flex-col gap-4 bg-surface-inverse p-7"
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-control bg-forest-800 text-forest-200">
                <Icon icon={pillar.icon} size="md" />
              </span>

              <Heading as="h3" size="sm" tone="inverse">
                {pillar.title}
              </Heading>

              <Text size="sm" tone="inverse-muted">
                {pillar.body}
              </Text>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}

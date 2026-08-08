import { Check, Mic, Sparkles } from "lucide-react";
import { Badge, Heading, Icon, Text } from "@/components/ui";
import { cn } from "@/lib/cn";
import { Container, Section, SectionHeader } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * The four numbered circles with a hairline connector were the weakest
 * thing on the old page: four equal blobs of text that told no story and
 * showed nothing of the product.
 *
 * This is an alternating narrative instead -- copy one side, a real piece
 * of product UI the other, sides swapping down the page. Each step gets a
 * DIFFERENT visual, because showing the same ranked list four times would
 * be worse than showing nothing.
 * ------------------------------------------------------------------ */

/** Step 1 — the profile form. */
function ProfileVisual() {
  const fields = [
    { label: "Degree", value: "BSc Computer Science" },
    { label: "GPA", value: "3.6 / 4.0" },
    { label: "IELTS", value: "7.0" },
    { label: "Target countries", value: "Germany, Netherlands" },
  ];

  return (
    <div className="rounded-card border border-border bg-surface p-5 shadow-e1">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-fg">Your profile</span>
        <Badge tone="success" size="sm" variant="subtle">
          Complete
        </Badge>
      </div>
      <dl className="mt-4 flex flex-col gap-2.5">
        {fields.map((field) => (
          <div
            key={field.label}
            className="flex items-center justify-between gap-4 rounded-control bg-canvas px-3 py-2.5"
          >
            <dt className="text-xs text-fg-subtle">{field.label}</dt>
            <dd className="truncate text-sm font-medium text-fg">
              {field.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Step 2 — why a match scored what it scored. */
function ScoreVisual() {
  const factors = [
    { label: "Academic fit", value: 95 },
    { label: "Language requirement", value: 88 },
    { label: "Deadline feasibility", value: 74 },
  ];

  return (
    <div className="rounded-card border border-border bg-surface p-5 shadow-e1">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-fg">TU Munich</p>
          <p className="truncate text-xs text-fg-subtle">
            MSc Artificial Intelligence
          </p>
        </div>
        <div className="shrink-0 text-right">
          <span className="font-serif text-2xl font-semibold text-brand-fg">
            92%
          </span>
          <span className="block text-xs text-fg-subtle">match</span>
        </div>
      </div>

      <div className="mt-5 flex flex-col gap-3 border-t border-border pt-4">
        {factors.map((factor) => (
          <div key={factor.label} className="flex items-center gap-3">
            <span className="w-36 shrink-0 text-xs text-fg-muted">
              {factor.label}
            </span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-canvas-inset">
              <span
                className="block h-full rounded-full bg-brand"
                style={{ width: `${factor.value}%` }}
              />
            </span>
            <span className="w-8 shrink-0 text-right text-xs font-semibold tabular-nums text-fg">
              {factor.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Step 3 — the phased checklist timeline. */
function TimelineVisual() {
  const phases = [
    { name: "Language prep", done: 3, total: 3 },
    { name: "Documents", done: 4, total: 6 },
    { name: "Application", done: 0, total: 5 },
    { name: "Post-acceptance", done: 0, total: 4 },
  ];

  return (
    <div className="rounded-card border border-border bg-surface p-5 shadow-e1">
      <span className="text-sm font-semibold text-fg">
        TU Munich — application plan
      </span>

      <ol className="mt-4 flex flex-col">
        {phases.map((phase, i) => {
          const complete = phase.done === phase.total;
          const started = phase.done > 0;
          return (
            <li key={phase.name} className="flex gap-3">
              {/* Rail */}
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2",
                    complete
                      ? "border-brand bg-brand text-fg-on-brand"
                      : started
                        ? "border-brand bg-surface"
                        : "border-border-strong bg-surface",
                  )}
                >
                  {complete && <Icon icon={Check} size="xs" className="h-3 w-3" />}
                </span>
                {i < phases.length - 1 && (
                  <span
                    className={cn(
                      "w-0.5 flex-1",
                      complete ? "bg-brand" : "bg-border",
                    )}
                  />
                )}
              </div>

              <div className="flex-1 pb-5">
                <div className="flex items-center justify-between gap-3">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      started ? "text-fg" : "text-fg-subtle",
                    )}
                  >
                    {phase.name}
                  </span>
                  <span className="text-xs tabular-nums text-fg-subtle">
                    {phase.done}/{phase.total}
                  </span>
                </div>
                <span className="mt-2 block h-1 overflow-hidden rounded-full bg-canvas-inset">
                  <span
                    className="block h-full rounded-full bg-brand"
                    style={{ width: `${(phase.done / phase.total) * 100}%` }}
                  />
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** Step 4 — writing feedback with inline corrections. */
function FeedbackVisual() {
  return (
    <div className="rounded-card border border-border bg-surface p-5 shadow-e1">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-fg">Writing Task 2</span>
        <Badge tone="brand" size="sm" icon={Sparkles}>
          AI scored
        </Badge>
      </div>

      <p className="mt-4 rounded-control bg-canvas p-3 text-sm leading-6 text-fg-muted">
        In conclusion, goverments should{" "}
        <span className="rounded-[4px] bg-danger-subtle px-1 text-danger-fg underline decoration-danger decoration-wavy underline-offset-2">
          invests
        </span>{" "}
        more in public transport, which{" "}
        <span className="rounded-[4px] bg-warning-subtle px-1 text-warning-fg">
          is a thing that
        </span>{" "}
        reduces congestion.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-2">
        {[
          { label: "Task response", band: "7.0" },
          { label: "Coherence", band: "6.5" },
          { label: "Lexical resource", band: "6.5" },
          { label: "Grammar", band: "6.0" },
        ].map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between rounded-control bg-canvas px-3 py-2"
          >
            <span className="truncate text-xs text-fg-subtle">
              {item.label}
            </span>
            <span className="text-sm font-semibold tabular-nums text-fg">
              {item.band}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2 text-xs text-fg-subtle">
        <Icon icon={Mic} size="xs" />
        Speaking sessions are scored live, the same way.
      </div>
    </div>
  );
}

const STEPS = [
  {
    number: "01",
    title: "Tell Dalil who you are",
    body: "Enter your degree, GPA and target countries — or upload your CV and let Dalil read them out of it. This is the only form you fill in.",
    visual: <ProfileVisual />,
  },
  {
    number: "02",
    title: "See where you actually stand",
    body: "Every programme comes back with a computed confidence score and the factors behind it, so you know which applications are realistic and which are a stretch.",
    visual: <ScoreVisual />,
  },
  {
    number: "03",
    title: "Turn a match into a plan",
    body: "One click expands any programme into a phased checklist — documents, language certificates, financial proof, deadlines and the steps that come after an offer.",
    visual: <TimelineVisual />,
  },
  {
    number: "04",
    title: "Close the gap on IELTS",
    body: "Sit full exam simulations across all four skills. Writing and Speaking come back with band scores and inline feedback, not just a number.",
    visual: <FeedbackVisual />,
  },
];

export function HowItWorks() {
  return (
    <Section id="how-it-works" tone="canvas" labelledBy="how-it-works-heading">
      <Container>
        <SectionHeader
          id="how-it-works-heading"
          eyebrow="How it works"
          title="From first search to submitted application"
          lead="Four steps. The first one takes two minutes; Dalil does the compounding work after that."
        />

        <div className="mt-16 flex flex-col gap-20 lg:gap-28">
          {STEPS.map((step, i) => {
            const flipped = i % 2 === 1;
            return (
              <div
                key={step.number}
                className="grid items-center gap-10 lg:grid-cols-12 lg:gap-16"
              >
                {/* Copy */}
                <Reveal
                  className={cn(
                    "lg:col-span-5",
                    flipped ? "lg:order-2 lg:col-start-8" : "lg:order-1",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className="font-serif text-5xl font-semibold text-brand/15"
                  >
                    {step.number}
                  </span>

                  <Heading as="h3" size="lg" className="mt-3">
                    {step.title}
                  </Heading>

                  <Text tone="muted" className="mt-4">
                    {step.body}
                  </Text>
                </Reveal>

                {/* Visual */}
                <Reveal
                  delay={120}
                  className={cn(
                    "lg:col-span-6",
                    flipped ? "lg:order-1 lg:col-start-1" : "lg:order-2",
                  )}
                >
                  {step.visual}
                </Reveal>
              </div>
            );
          })}
        </div>
      </Container>
    </Section>
  );
}

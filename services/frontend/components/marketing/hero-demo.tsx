import { Sparkles } from "lucide-react";
import { Badge, Icon, Progress, Text } from "@/components/ui";
import { Enter } from "./enter";

/* ------------------------------------------------------------------ *
 * The product demo. This is the single most looked-at element on the
 * page, so it is built as real DOM rather than a screenshot: sharp at
 * any density, themeable, weightless over the network, and it cannot go
 * stale against the real UI the way an exported image does.
 *
 * Country chips rather than flag emoji: emoji flags do not render on
 * Windows, where they degrade to bare letter pairs ("DE", "NL") -- which
 * is exactly how the previous hero looked on most desktop visits.
 * ------------------------------------------------------------------ */

const MATCHES = [
  {
    code: "DE",
    country: "Germany",
    university: "TU Munich",
    programme: "MSc Artificial Intelligence",
    score: 92,
  },
  {
    code: "NL",
    country: "Netherlands",
    university: "TU Delft",
    programme: "MSc Data Science",
    score: 88,
  },
  {
    code: "SE",
    country: "Sweden",
    university: "KTH Stockholm",
    programme: "MSc Computer Science",
    score: 84,
  },
];

function CountryChip({ code, country }: { code: string; country: string }) {
  return (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-brand-muted text-xs font-semibold tracking-wide text-brand-fg"
      title={country}
    >
      <span aria-hidden="true">{code}</span>
      <span className="sr-only">{country}</span>
    </span>
  );
}

export function HeroDemo() {
  return (
    <div className="relative lg:pt-20">
      {/* The lg:pt-20 above reserves genuine empty space for the "Top
          match" widget to float in, on the outer box so it's padding
          (which reserves real layout space) rather than a child's margin
          (which would collapse into this box's own top edge and put the
          widget right back on the header). Everything decorative (glow,
          edge-peek, tilt) lives inside this positioned wrapper so it
          travels with the card. */}
      <div className="relative">
        <div
          aria-hidden="true"
          className="absolute -inset-x-6 -inset-y-8 -z-10 rounded-[3rem] bg-brand/5 blur-2xl"
        />
        <div
          aria-hidden="true"
          className="absolute inset-x-6 -top-3 -z-10 h-8 rounded-t-panel border border-border bg-surface/60"
        />

        {/* A one-degree static tilt, not an animation, is what stops the
            card reading as a flat screenshot pasted onto the page -- the
            same "product shot at a poised angle" device premium SaaS
            marketing sites use. It settles upright on hover as a small
            reward for attention, and the whole thing is inert under
            prefers-reduced-motion via the global transition rule. */}
        <div className="rotate-1 transition-transform duration-500 ease-out hover:rotate-0">
          <div className="overflow-hidden rounded-panel border border-brand-border bg-surface shadow-e4 ring-1 ring-brand/10">
            {/* Header */}
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-fg-on-brand">
                  <Icon icon={Sparkles} size="xs" />
                </span>
                <span className="text-sm font-semibold text-fg">
                  Dalil Assistant
                </span>
              </div>
              <Badge tone="success" variant="subtle" size="sm" dot>
                Online
              </Badge>
            </div>

            <div className="flex flex-col gap-4 p-5">
              {/* User turn */}
              <Enter className="flex justify-end" delay={100}>
                <p className="max-w-[17rem] rounded-card rounded-br-sm bg-brand px-4 py-2.5 text-sm leading-6 text-fg-on-brand">
                  Find me AI Master&apos;s programmes in Europe I can
                  actually get into.
                </p>
              </Enter>

              {/* Assistant turn */}
              <Enter delay={220}>
                <Text size="sm" tone="muted" className="mb-3">
                  Based on your 3.6 GPA and IELTS 7.0, here are your
                  strongest matches:
                </Text>

                <ul className="flex flex-col gap-2">
                  {MATCHES.map((match, i) => (
                    <Enter
                      as="li"
                      key={match.university}
                      delay={340 + i * 90}
                      className="flex items-center gap-3 rounded-card border border-border bg-canvas p-3"
                    >
                      <CountryChip
                        code={match.code}
                        country={match.country}
                      />

                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-fg">
                          {match.university}
                        </p>
                        <p className="truncate text-xs text-fg-subtle">
                          {match.programme}
                        </p>
                      </div>

                      {/* A chip, not a number over a progress bar. At this
                          size the bar sat directly under the figure and
                          read as an underline rather than a meter; the
                          ranked comparison is already carried by the order
                          of the rows. The bar treatment stays in Features,
                          where there is room -- and now also lives on the
                          floating "Top match" widget above, which has the
                          space for it. */}
                      <span className="shrink-0 rounded-chip bg-brand-muted px-2 py-1 text-xs font-semibold tabular-nums text-brand-fg">
                        {match.score}% match
                      </span>
                    </Enter>
                  ))}
                </ul>
              </Enter>

              {/* Composer hint */}
              <Enter delay={640}>
                <div className="flex items-center justify-between gap-3 rounded-control border border-border bg-canvas px-4 py-2.5">
                  <span className="text-sm text-fg-subtle">
                    Ask a follow-up&hellip;
                  </span>
                  <span className="flex h-6 w-6 items-center justify-center rounded-chip bg-canvas-inset text-xs font-medium text-fg-subtle">
                    ↵
                  </span>
                </div>
              </Enter>
            </div>
          </div>
        </div>

        {/* Bottom-right accent chip — breaks the card's rectangle, which
            is what keeps the composition from reading as a flat
            screenshot. Straddles the corner rather than floating over the
            content, where it previously covered the third match row. */}
        <Enter
          delay={780}
          className="absolute -right-4 -bottom-4 hidden sm:block"
        >
          <div className="flex items-center gap-2 rounded-control border border-border bg-surface px-3 py-2 shadow-e2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-subtle text-accent-fg">
              <Icon icon={Sparkles} size="xs" />
            </span>
            <span className="text-xs font-semibold text-fg">
              Checklist ready
            </span>
          </div>
        </Enter>
      </div>

      {/* Top match widget. Lives in the empty air the lg:mt-20 push
          reserves above the card, so it is a second, independent focal
          point rather than an overlay on top of the header -- the
          layered "floating UI chips around a product shot" look of a
          polished SaaS hero instead of a single flat rectangle. Echoes
          the top row already shown inside the chat rather than
          asserting a new number, so it isn't a claim the demo doesn't
          already back up. */}
      <Enter
        delay={460}
        className="absolute top-0 left-6 hidden w-44 lg:block"
      >
        <div className="rounded-card border border-border bg-surface p-3.5 shadow-e2">
          <div className="flex items-center justify-between gap-2">
            <Text size="xs" tone="subtle" weight="medium">
              Top match
            </Text>
            <span className="text-xs font-semibold tabular-nums text-brand-fg">
              {MATCHES[0].score}%
            </span>
          </div>
          <p className="mt-1 truncate text-sm font-semibold text-fg">
            {MATCHES[0].university}
          </p>
          <Progress
            value={MATCHES[0].score}
            size="sm"
            label={`${MATCHES[0].university} match score`}
            className="mt-2.5"
          />
        </div>
      </Enter>
    </div>
  );
}

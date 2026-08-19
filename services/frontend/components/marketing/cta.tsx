import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Button, Heading, Icon, Text } from "@/components/ui";
import { Container, Section } from "./section";
import { Reveal } from "./reveal";

const REASSURANCE = [
  "Free forever tier",
  "No card required",
  "2-minute setup",
  "Delete your data any time",
];

/**
 * The closing ask, and visually the heaviest moment on the page after the
 * hero. It runs straight into the footer, which sits a shade darker again —
 * so the page deepens as it ends rather than trailing off into a thin white
 * band, which is how the previous landing page finished.
 *
 * The old page had no closing CTA at all: it ended on a pricing table and
 * dropped into the footer.
 */
export function CTA() {
  return (
    <Section
      tone="inverse"
      labelledBy="cta-heading"
      className="overflow-hidden text-center"
    >
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-grid-inverse [mask-image:radial-gradient(ellipse_50%_60%_at_50%_50%,black,transparent)]" />
        {/* Warm glow, so the closing moment is inviting rather than austere. */}
        <div className="absolute top-1/2 left-1/2 h-[30rem] w-[46rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute -bottom-32 left-1/2 h-[24rem] w-[24rem] -translate-x-1/2 rounded-full bg-forest-400/10 blur-3xl" />
      </div>

      <Container>
        <Reveal className="mx-auto flex max-w-2xl flex-col items-center">
          <span className="text-xs font-semibold tracking-[0.08em] text-sand-300 uppercase">
            Applications are already open
          </span>

          <Heading
            as="h2"
            id="cta-heading"
            size="2xl"
            tone="inverse"
            className="mt-5"
          >
            Your programme is out there. Go and find it.
          </Heading>

          <Text size="lg" tone="inverse-muted" className="mt-5">
            Build your profile in two minutes and see your ranked matches
            today.
          </Text>

          <div className="mt-9 flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            <Button asChild size="lg" variant="inverse" trailingIcon={ArrowRight}>
              <Link href="/register">Get started free</Link>
            </Button>
            {/* Given a visible outline: on a dark field, a bare text button
                beside a solid white one reads as a caption rather than as a
                second choice. */}
            <Button
              asChild
              size="lg"
              variant="ghost"
              className="border border-white/25 text-fg-inverse hover:border-white/40 hover:bg-white/10 hover:text-fg-inverse focus-visible:outline-sand-300"
            >
              <Link href="#how-it-works">See how it works</Link>
            </Button>
          </div>

          <ul className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
            {REASSURANCE.map((item) => (
              <li
                key={item}
                className="flex items-center gap-1.5 text-sm text-fg-inverse-muted"
              >
                <Icon icon={Check} size="xs" className="text-forest-300" />
                {item}
              </li>
            ))}
          </ul>
        </Reveal>
      </Container>
    </Section>
  );
}

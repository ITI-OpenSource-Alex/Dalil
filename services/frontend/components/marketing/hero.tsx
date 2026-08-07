import Link from "next/link";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import { Badge, Button, Heading, Icon, Text } from "@/components/ui";
import { cn } from "@/lib/cn";
import { Container } from "./section";
import { Enter } from "./enter";
import { HeroDemo } from "./hero-demo";

const STATS = [
  { value: 120, suffix: "+", label: "Universities indexed" },
  { value: 30, suffix: "+", label: "Destination countries" },
  { value: 4, suffix: "", label: "IELTS skills scored" },
];

const REASSURANCE = ["Free forever plan", "No card required", "2-minute setup"];

export function Hero() {
  return (
    <section
      aria-labelledby="hero-heading"
      className="relative isolate overflow-hidden bg-canvas pt-20 pb-24 sm:pt-24 lg:pt-32 lg:pb-36"
    >
      {/* ---------------------------------------------------------------
          Background. Three flat layers instead of a template-looking
          linear gradient. Everything here is CSS: no images, no JS. The
          glows are sized and placed to sit directly behind the two things
          that need the most visual weight -- the headline and the demo
          card -- rather than as generic corner decoration.
          --------------------------------------------------------------- */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        {/* Blueprint grid, masked to a soft oval so it never tiles to the
            edges. */}
        <div className="absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)] opacity-60" />
        {/* Brand glow behind the headline. */}
        <div className="absolute -top-32 -left-40 h-[36rem] w-[36rem] rounded-full bg-brand/8 blur-3xl" />
        {/* Warm counterweight behind the demo, larger and slightly lower
            than before so it reads as the light source the tilted card is
            catching, rather than a flat corner tint. */}
        <div className="absolute top-8 right-[-6rem] h-[34rem] w-[34rem] rounded-full bg-accent/10 blur-3xl" />
      </div>

      <Container>
        {/* 7/5 rather than 6/6: the headline needs the wider column. At an
            even split "Smarter with AI" could not fit on one line at any
            respectable display size, and orphaned "AI" onto a third line. */}
        <div className="grid items-center gap-y-16 lg:grid-cols-12 lg:gap-x-10">
          {/* ------------------------------------------------ Copy */}
          <div className="lg:col-span-7">
            <Enter>
              <Badge
                tone="brand"
                variant="outline"
                size="lg"
                icon={Sparkles}
                pill
                className="bg-surface/80 backdrop-blur-sm"
              >
                The AI study abroad platform
              </Badge>
            </Enter>

            <Enter delay={80}>
              {/* Sized so "Smarter with AI" holds one line at every
                  breakpoint. balance is off because the line break is
                  explicit -- the balancer would fight it. Pushed a step
                  larger than the previous pass on xl+ screens, where the
                  wider column has room for the display scale the `3xl`
                  token is actually built for. */}
              <Heading
                as="h1"
                id="hero-heading"
                size="3xl"
                balance={false}
                className="mt-7 text-4xl sm:text-5xl lg:text-6xl xl:text-7xl"
              >
                Study Abroad
                <br />
                {/* The warm stop is pushed to 55% so the phrase stays brand
                    green for most of its length and only lifts to amber at
                    the end. An evenly-spaced three-stop gradient put "with"
                    in the muddy olive midpoint between green and gold. */}
                <span className="bg-gradient-to-r from-brand from-20% via-forest-600 via-55% to-accent bg-clip-text text-transparent">
                  Smarter with AI
                </span>
              </Heading>
            </Enter>

            <Enter delay={160}>
              <Text size="lg" tone="muted" className="mt-6 max-w-lg">
                Find the programmes you will actually get into, turn each one
                into a step-by-step application checklist, and train for IELTS
                — with one assistant that already knows your profile.
              </Text>
            </Enter>

            <Enter delay={240}>
              <div className="relative mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
                {/* Soft glow seated behind the primary action only, so the
                    eye lands there first. Same device as the background
                    glows above, just scaled down to button size. */}
                <div
                  aria-hidden="true"
                  className="absolute top-1/2 left-0 -z-10 h-16 w-40 -translate-y-1/2 rounded-full bg-brand/20 blur-2xl"
                />
                <Button
                  asChild
                  size="lg"
                  trailingIcon={ArrowRight}
                  className={cn(
                    "group transition-[background-color,border-color,color,box-shadow,transform] duration-200 ease-out",
                    "hover:-translate-y-0.5 hover:shadow-e2",
                    "[&_svg]:transition-transform [&_svg]:duration-200 [&_svg]:ease-out group-hover:[&_svg]:translate-x-0.5",
                  )}
                >
                  <Link href="/register">Get started free</Link>
                </Button>
                <Button asChild size="lg" variant="secondary">
                  <Link href="#how-it-works">See how it works</Link>
                </Button>
              </div>
            </Enter>

            <Enter delay={300}>
              <ul className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2">
                {REASSURANCE.map((item) => (
                  <li
                    key={item}
                    className="flex items-center gap-1.5 text-sm text-fg-subtle"
                  >
                    <Icon icon={Check} size="xs" className="text-success" />
                    {item}
                  </li>
                ))}
              </ul>
            </Enter>

            {/* Stats, upgraded from a ruled-off text row to individually
                boxed metrics -- the same "this is a real product with real
                numbers" cue a SaaS dashboard widget gives, built from
                nothing but the existing card border/radius tokens. */}
            <Enter delay={360}>
              <dl className="mt-12 grid grid-cols-3 gap-3 sm:gap-4">
                {STATS.map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-card border border-border bg-surface/60 px-3 py-3.5 backdrop-blur-sm transition-colors duration-200 ease-out hover:border-border-strong sm:px-5 sm:py-4"
                  >
                    <dd className="font-serif text-2xl font-semibold tabular-nums text-fg sm:text-3xl">
                      {stat.value}
                      {stat.suffix}
                    </dd>
                    <dt className="mt-1 text-xs text-fg-subtle sm:text-sm">
                      {stat.label}
                    </dt>
                  </div>
                ))}
              </dl>
            </Enter>
          </div>

          {/* ------------------------------------------------ Demo */}
          <div className="lg:col-span-5 lg:border-l lg:border-border lg:pl-10">
            <HeroDemo />
          </div>
        </div>
      </Container>
    </section>
  );
}

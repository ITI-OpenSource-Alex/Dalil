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
      className="relative isolate overflow-hidden bg-canvas pt-16 pb-20 sm:pt-20 lg:pt-28 lg:pb-32"
    >
      {/* ---------------------------------------------------------------
          Background. Three flat layers instead of the previous three-colour
          linear gradient, which is the most template-looking element a
          landing page can have. Everything here is CSS: no images, no JS.
          --------------------------------------------------------------- */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        {/* Blueprint grid, masked to a soft oval so it never tiles to the
            edges. */}
        <div className="absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)] opacity-60" />
        {/* Brand glow behind the headline. */}
        <div className="absolute -top-32 -left-40 h-[36rem] w-[36rem] rounded-full bg-brand/8 blur-3xl" />
        {/* Warm counterweight on the demo side, so the composition is not
            symmetrical. */}
        <div className="absolute -top-20 right-0 h-[28rem] w-[28rem] rounded-full bg-accent/8 blur-3xl" />
      </div>

      <Container>
        {/* 7/5 rather than 6/6: the headline needs the wider column. At an
            even split "Smarter with AI" could not fit on one line at any
            respectable display size, and orphaned "AI" onto a third line. */}
        <div className="grid items-center gap-16 lg:grid-cols-12 lg:gap-12">
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
                  explicit -- the balancer would fight it. */}
              <Heading
                as="h1"
                id="hero-heading"
                size="3xl"
                balance={false}
                className="mt-6 text-4xl sm:text-5xl lg:text-6xl"
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
              <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
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

            {/* Stats. Ruled off rather than floating, so they read as a
                footer to the copy block instead of a fourth element. */}
            <Enter delay={360}>
              <dl className="mt-10 flex gap-8 border-t border-border pt-8 sm:gap-12">
                {STATS.map((stat) => (
                  <div key={stat.label}>
                    <dt className="sr-only">{stat.label}</dt>
                    <dd>
                      <span className="block font-serif text-3xl font-semibold tabular-nums text-fg">
                        {stat.value}
                        {stat.suffix}
                      </span>
                      <span className="mt-1 block text-sm text-fg-subtle">
                        {stat.label}
                      </span>
                    </dd>
                  </div>
                ))}
              </dl>
            </Enter>
          </div>

          {/* ------------------------------------------------ Demo */}
          <div className="lg:col-span-5">
            <HeroDemo />
          </div>
        </div>
      </Container>
    </section>
  );
}

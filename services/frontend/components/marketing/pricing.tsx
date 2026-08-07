import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Badge, Button, Heading, Icon, Text } from "@/components/ui";
import { cn } from "@/lib/cn";
import { Container, Section, SectionHeader } from "./section";
import { Reveal } from "./reveal";

const TIERS = [
  {
    name: "Free",
    tagline: "Everything you need to find a programme and plan the application.",
    price: "$0",
    period: "forever",
    features: [
      "AI opportunity matching with confidence scores",
      "Personalised application checklists",
      "Unlimited chat with GOA",
      "CV upload and profile extraction",
    ],
    cta: "Get started free",
    href: "/register",
    featured: false,
  },
  {
    name: "GOA Pro",
    tagline: "Full IELTS preparation with AI feedback across every skill.",
    price: "$7",
    period: "per month",
    features: [
      "Everything in Free",
      "Full IELTS exam simulations, all four skills",
      "Speaking practice with live transcription",
      "Writing evaluation with inline corrections",
      "CV review and rewrite suggestions",
    ],
    cta: "Start with Pro",
    href: "/register",
    featured: true,
  },
];

export function Pricing() {
  return (
    <Section id="pricing" tone="subtle" labelledBy="pricing-heading">
      <Container>
        <SectionHeader
          id="pricing-heading"
          align="center"
          eyebrow="Pricing"
          title="Start free. Upgrade when IELTS gets real."
          lead="Matching and checklists are free forever. You only pay when you want the exam simulations and AI band scoring."
        />

        <div className="mx-auto mt-14 grid max-w-4xl items-stretch gap-6 lg:grid-cols-2">
          {TIERS.map((tier, i) => (
            <Reveal
              as="article"
              key={tier.name}
              delay={i * 100}
              className={cn(
                "flex flex-col rounded-card p-8",
                tier.featured
                  ? // Emphasis by tint and elevation rather than a heavy
                    // outline, which reads as a validation error at a glance.
                    "border border-brand-border bg-surface shadow-e3 ring-1 ring-brand/10"
                  : "border border-border bg-surface",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <Heading as="h3" size="md">
                  {tier.name}
                </Heading>
                {tier.featured && (
                  <Badge tone="brand" variant="solid" size="md">
                    Most popular
                  </Badge>
                )}
              </div>

              <Text size="sm" tone="muted" className="mt-2 min-h-[3rem]">
                {tier.tagline}
              </Text>

              <p className="mt-6 flex items-baseline gap-2">
                <span className="font-serif text-5xl font-semibold tracking-tight text-fg">
                  {tier.price}
                </span>
                <span className="text-sm text-fg-subtle">{tier.period}</span>
              </p>

              <ul className="mt-8 flex flex-col gap-3.5">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
                      <Icon icon={Check} size="xs" className="h-3 w-3" />
                    </span>
                    <Text as="span" size="sm" tone="muted">
                      {feature}
                    </Text>
                  </li>
                ))}
              </ul>

              {/* mt-auto pins the action to the bottom, so the two cards'
                  buttons align no matter how many features each lists. */}
              <div className="mt-auto pt-8">
                <Button
                  asChild
                  fullWidth
                  size="lg"
                  variant={tier.featured ? "primary" : "secondary"}
                  trailingIcon={tier.featured ? ArrowRight : undefined}
                >
                  <Link href={tier.href}>{tier.cta}</Link>
                </Button>

                {/* Reassurance sits under the button, where the hesitation
                    actually happens -- not buried in the section intro. */}
                <p className="mt-3 text-center text-xs text-fg-subtle">
                  {tier.featured
                    ? "Cancel any time. No card required to try the free tier first."
                    : "No credit card required."}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </Container>
    </Section>
  );
}

import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { Badge, Button, Heading, Icon, Text } from "@/components/ui";
import { cn } from "@/lib/cn";
import { PRICING_PLANS } from "@/lib/pricing-plans";
import { Container, Section, SectionHeader } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * The landing page's pricing section.
 *
 * The tier data moved to lib/pricing-plans.ts in GOA-039, where /pricing
 * reads the same copy. This file owns the presentation of it and nothing
 * else -- the two surfaces cannot drift apart on what $7 buys.
 *
 * Still a Server Component: no "use client", no hooks. `signedIn` is passed
 * down from app/page.tsx, which already reads the cookie on the server, so
 * the section can send an existing account to /pricing (where their real
 * tier and an actual upgrade action live) instead of to a registration form
 * they have no use for.
 * ------------------------------------------------------------------ */

export function Pricing({ signedIn = false }: { signedIn?: boolean }) {
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
          {PRICING_PLANS.map((plan, i) => {
            // A visitor with a session already has an account, so "Get
            // started free" / "Start with Pro" are both wrong for them.
            // /pricing is the surface that knows their actual tier.
            const cta = signedIn
              ? {
                  label: plan.featured ? "Upgrade to Dalil Pro" : "See your plan",
                  href: "/pricing",
                }
              : plan.signedOutCta;

            return (
              <Reveal
                as="article"
                key={plan.id}
                delay={i * 100}
                className={cn(
                  "flex flex-col rounded-card p-8",
                  plan.featured
                    ? // Emphasis by tint and elevation rather than a heavy
                      // outline, which reads as a validation error at a glance.
                      "border border-brand-border bg-surface shadow-e3 ring-1 ring-brand/10"
                    : "border border-border bg-surface",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <Heading as="h3" size="md">
                    {plan.name}
                  </Heading>
                  {plan.featured && (
                    <Badge tone="brand" variant="solid" size="md">
                      Most popular
                    </Badge>
                  )}
                </div>

                <Text size="sm" tone="muted" className="mt-2 min-h-[3rem]">
                  {plan.tagline}
                </Text>

                <p className="mt-6 flex items-baseline gap-2">
                  <span className="font-serif text-5xl font-semibold tracking-tight text-fg">
                    {plan.price}
                  </span>
                  <span className="text-sm text-fg-subtle">{plan.period}</span>
                </p>

                <ul className="mt-8 flex flex-col gap-3.5">
                  {plan.features.map((feature) => (
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
                    variant={plan.featured ? "primary" : "secondary"}
                    trailingIcon={plan.featured ? ArrowRight : undefined}
                  >
                    <Link href={cta.href}>{cta.label}</Link>
                  </Button>

                  {/* Reassurance sits under the button, where the hesitation
                      actually happens -- not buried in the section intro. */}
                  <p className="mt-3 text-center text-xs text-fg-subtle">
                    {plan.note}
                  </p>
                </div>
              </Reveal>
            );
          })}
        </div>

        <p className="mt-10 text-center text-sm text-fg-subtle">
          <Link
            href="/pricing"
            className="text-brand-fg underline underline-offset-4 decoration-brand-border hover:decoration-brand-fg"
          >
            Compare the plans in full
          </Link>
        </p>
      </Container>
    </Section>
  );
}

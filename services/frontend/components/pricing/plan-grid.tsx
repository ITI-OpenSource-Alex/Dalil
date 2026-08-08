"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";
import { PRICING_PLANS, type PricingPlan } from "@/lib/pricing-plans";
import {
  billingEnabled,
  createCheckoutSession,
  isBillingAuthError,
  isBillingConflictError,
  isBillingUnavailableError,
  redirectTo,
} from "@/lib/billing-api";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import {
  Alert,
  Badge,
  Button,
  Heading,
  Icon,
  Text,
} from "@/components/ui";
import { Container, Section, SectionHeader } from "@/components/marketing/section";

/* ------------------------------------------------------------------ *
 * /pricing — the upgrade surface (GOA-039).
 *
 * The card layout is deliberately the same composition as the landing
 * page's pricing section: same tier data (lib/pricing-plans.ts), same
 * primitives, same rhythm. What differs is the action, which here depends
 * on who is asking.
 *
 * Reveal is not used. The scroll-reveal wrapper ships its hidden state in
 * the HTML and relies on app/page.tsx's <noscript> override to restore it;
 * this page is short enough that everything is above the fold anyway, and
 * a paywall that can flash blank is not worth 16px of animation.
 * ------------------------------------------------------------------ */

type Action =
  | { kind: "link"; label: string; href: string }
  | { kind: "current"; label: string }
  | { kind: "checkout" }
  | { kind: "manage" }
  | { kind: "unavailable"; label: string };

export function PricingPlans({ signedIn }: { signedIn: boolean }) {
  return (
    <Section tone="subtle" labelledBy="pricing-page-heading">
      <Container>
        <SectionHeader
          id="pricing-page-heading"
          align="center"
          eyebrow="Pricing"
          title="Start free. Upgrade when IELTS gets real."
          lead="Matching, checklists and chat are free forever. Dalil Pro adds the full IELTS exam simulations and AI band scoring."
        />

        {/* useSearchParams needs a boundary above it. The fallback is null
            because the notice is supplementary — the plans below render
            regardless. */}
        <Suspense fallback={null}>
          <CheckoutNotice />
        </Suspense>

        {signedIn ? <SignedInPlans /> : <SignedOutPlans />}

        <p className="mx-auto mt-12 max-w-xl text-center text-xs text-fg-subtle">
          Billing is simulated for this project. No payment is taken and no card
          details are stored.
        </p>
      </Container>
    </Section>
  );
}

/** `?checkout=cancelled` — the checkout page's Cancel returns the user here. */
function CheckoutNotice() {
  const params = useSearchParams();
  if (params.get("checkout") !== "cancelled") return null;

  return (
    <div className="mx-auto mt-10 max-w-2xl">
      <Alert tone="info" title="Payment cancelled" announce="polite">
        You have not been charged. Your account is unchanged — pick a plan
        below whenever you are ready.
      </Alert>
    </div>
  );
}

/**
 * An anonymous visitor. No profile request is made: there is no session to
 * describe, and a 401 on a public marketing route is noise.
 */
function SignedOutPlans() {
  return (
    <PlanCards
      actionFor={(plan) => ({
        kind: "link",
        label: plan.signedOutCta.label,
        href: plan.signedOutCta.href,
      })}
    />
  );
}

/** A signed-in visitor. The action depends on the tier the server reports. */
function SignedInPlans() {
  const { user, status, error, retry } = useCurrentUser();
  const [busy, setBusy] = useState<"checkout" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Never guess while identity is in flight. Assuming Free would offer a
  // paying subscriber the chance to buy what they already have; assuming
  // Paid would hide the only action a Free user came here for.
  const identityKnown = status === "success" && user !== null;
  const isPaid = identityKnown && user.subscriptionTier === "paid";

  async function startCheckout() {
    // Belt and braces alongside the disabled button: a double-click that lands
    // before React re-renders would otherwise open two checkout sessions.
    // lib/billing-api.ts dedupes the request itself as well.
    if (busy) return;
    setBusy("checkout");
    setActionError(null);
    try {
      const { url } = await createCheckoutSession();
      redirectTo(url);
      // Deliberately no setBusy(null): the browser is leaving. Clearing it
      // would re-enable the button for the moment before navigation.
    } catch (err) {
      setBusy(null);
      if (isBillingConflictError(err)) {
        // They already have it -- almost always a second tab that upgraded.
        // Re-read the profile so the page corrects itself to the paid state.
        setActionError(err.message);
        void retry();
      } else if (isBillingUnavailableError(err) || isBillingAuthError(err)) {
        setActionError(err.message);
      } else {
        setActionError(
          err instanceof Error && err.message
            ? err.message
            : "Something went wrong starting your upgrade. Please try again.",
        );
      }
    }
  }

  const actionFor = (plan: PricingPlan): Action => {
    if (plan.id === "free") {
      return isPaid
        ? { kind: "link", label: "Included in Dalil Pro", href: "/dashboard" }
        : { kind: "current", label: "Your current plan" };
    }

    if (!identityKnown) {
      // Loading or failed — PlanCards renders this as a busy button rather
      // than an action that might be wrong.
      return { kind: "unavailable", label: "Upgrade to Dalil Pro" };
    }

    if (isPaid) return { kind: "manage" };

    if (!billingEnabled()) {
      return { kind: "unavailable", label: "Upgrades coming soon" };
    }

    return { kind: "checkout" };
  };

  return (
    <>
      {status === "error" && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Alert
            tone="danger"
            actions={
              <>
                <Button variant="danger" size="sm" onClick={retry}>
                  Retry
                </Button>
                <Button variant="link" size="sm" asChild>
                  <Link href="/login">Log in again</Link>
                </Button>
              </>
            }
          >
            {error ?? "We couldn't load your account."}
          </Alert>
        </div>
      )}

      {isPaid && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Alert tone="success" title="You're on Dalil Pro" announce="none">
            Every paid feature is unlocked on this account. Use Manage
            subscription to review or cancel your plan.
          </Alert>
        </div>
      )}

      {actionError && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Alert tone="danger" onDismiss={() => setActionError(null)}>
            {actionError}
          </Alert>
        </div>
      )}

      {identityKnown && !isPaid && !billingEnabled() && (
        <div className="mx-auto mt-10 max-w-2xl">
          <Alert tone="info" title="Checkout isn't live yet" announce="none">
            Dalil Pro is not purchasable in this environment yet. Your Free plan
            keeps working exactly as it does today.
          </Alert>
        </div>
      )}

      <PlanCards
        actionFor={actionFor}
        busy={busy}
        onCheckout={startCheckout}
        highlightPlanId={isPaid ? "pro" : "free"}
      />
    </>
  );
}

function PlanCards({
  actionFor,
  busy = null,
  onCheckout,
  highlightPlanId,
}: {
  actionFor: (plan: PricingPlan) => Action;
  busy?: "checkout" | null;
  onCheckout?: () => void;
  /** Marks the plan the user is already on. */
  highlightPlanId?: string;
}) {
  return (
    <div className="mx-auto mt-12 grid max-w-4xl items-stretch gap-6 lg:grid-cols-2">
      {PRICING_PLANS.map((plan) => {
        const action = actionFor(plan);
        const isCurrent = highlightPlanId === plan.id;

        return (
          <article
            key={plan.id}
            className={cn(
              "flex flex-col rounded-card p-8",
              plan.featured
                ? "border border-brand-border bg-surface shadow-e3 ring-1 ring-brand/10"
                : "border border-border bg-surface",
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Heading as="h2" size="md">
                {plan.name}
              </Heading>
              <div className="flex items-center gap-2">
                {isCurrent && (
                  <Badge tone="neutral" size="md">
                    Current plan
                  </Badge>
                )}
                {plan.featured && (
                  <Badge tone="brand" variant="solid" size="md">
                    Most popular
                  </Badge>
                )}
              </div>
            </div>

            <Text size="sm" tone="muted" className="mt-2 min-h-12">
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

            <div className="mt-auto pt-8">
              <PlanAction
                action={action}
                featured={plan.featured}
                busy={busy}
                onCheckout={onCheckout}
              />
              <p className="mt-3 text-center text-xs text-fg-subtle">
                {plan.note}
              </p>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function PlanAction({
  action,
  featured,
  busy,
  onCheckout,
}: {
  action: Action;
  featured: boolean;
  busy: "checkout" | null;
  onCheckout?: () => void;
}) {
  const variant = featured ? "primary" : "secondary";

  switch (action.kind) {
    case "link":
      return (
        <Button
          asChild
          fullWidth
          size="lg"
          variant={variant}
          trailingIcon={featured ? ArrowRight : undefined}
        >
          <Link href={action.href}>{action.label}</Link>
        </Button>
      );

    case "current":
      return (
        <Button fullWidth size="lg" variant="secondary" disabled>
          {action.label}
        </Button>
      );

    case "checkout":
      return (
        <Button
          fullWidth
          size="lg"
          variant={variant}
          trailingIcon={ArrowRight}
          loading={busy === "checkout"}
          loadingLabel="Opening secure checkout"
          onClick={onCheckout}
        >
          Upgrade to Dalil Pro
        </Button>
      );

    case "manage":
      return (
        <Button asChild fullWidth size="lg" variant="secondary" leadingIcon={Sparkles}>
          <Link href="/billing/manage">Manage subscription</Link>
        </Button>
      );

    case "unavailable":
      return (
        <Button fullWidth size="lg" variant={variant} disabled>
          {action.label}
        </Button>
      );
  }
}

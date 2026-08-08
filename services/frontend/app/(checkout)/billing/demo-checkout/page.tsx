"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, CreditCard, Lock } from "lucide-react";
import {
  confirmDemoPayment,
  isBillingAuthError,
  isBillingConflictError,
  isBillingUnavailableError,
  redirectTo,
} from "@/lib/billing-api";
import {
  PAID_PLAN_NAME,
  PRO_PRICE_AMOUNT,
  PRO_PRICE_PERIOD,
  planById,
} from "@/lib/pricing-plans";
import {
  Alert,
  Button,
  Field,
  Heading,
  Icon,
  Input,
  Text,
} from "@/components/ui";

/* ------------------------------------------------------------------ *
 * /billing/demo-checkout — the payment step (GOA-039).
 *
 * A checkout, not an app page with a form on it. Two columns on desktop: what
 * you are paying for on one side, how you pay on the other, with the amount
 * repeated on the button so it is never more than one glance away. The
 * surrounding chrome is stripped back to the brand and one way out — see
 * app/(checkout)/layout.tsx.
 *
 * It is a *simulated* payment, and the page says so plainly without shouting:
 * a line under the heading and a note by the pay button. Nobody should type a
 * real card number here, and the surest way to prevent that is to make the
 * fixture cards the obvious thing to use — hence the small "Demo test cards"
 * helper, styled as a developer affordance rather than as the payment method.
 *
 * The page decides nothing. It posts the checkout token and whatever is in the
 * card field to the backend, which owns the token, knows whose checkout it is,
 * and is the only thing that can grant the tier. Expiry, CVC and cardholder
 * name are presentational: they make the form read like a checkout, they are
 * never sent, and no claim is made about them.
 * ------------------------------------------------------------------ */

const SUCCESS_CARD = "4242 4242 4242 4242";
const DECLINE_CARD = "4000 0000 0000 9995";

/** Groups digits in fours as the user types. The backend strips non-digits. */
function formatCardNumber(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 19);
  return digits.replace(/(.{4})/g, "$1 ").trim();
}

function formatExpiry(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)} / ${digits.slice(2)}`;
}

export default function DemoCheckoutPage() {
  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <Suspense
        fallback={
          <Text tone="muted" aria-busy="true">
            Loading checkout…
          </Text>
        }
      >
        <DemoCheckout />
      </Suspense>
    </div>
  );
}

function DemoCheckout() {
  const params = useSearchParams();
  const token = params.get("session") ?? "";

  // Prefilled from the success fixture so the demo is one click, and so the
  // first thing anyone sees in the card field is unmistakably not a real card.
  const [cardNumber, setCardNumber] = useState(SUCCESS_CARD);
  const [expiry, setExpiry] = useState("12 / 34");
  const [cvc, setCvc] = useState("123");
  const [cardholder, setCardholder] = useState("");

  const [busy, setBusy] = useState(false);
  const [declined, setDeclined] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function pay(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setDeclined(null);
    setError(null);

    try {
      const result = await confirmDemoPayment(token, cardNumber);

      if (result.status === "succeeded") {
        // Straight to the confirmation page, which does NOT take this as proof
        // of anything -- it re-reads the profile from the server.
        redirectTo(result.redirectUrl);
        return; // The browser is leaving; keep the button disabled.
      }

      setDeclined(result.message);
      setBusy(false);
    } catch (err) {
      setBusy(false);
      if (
        isBillingConflictError(err) ||
        isBillingUnavailableError(err) ||
        isBillingAuthError(err)
      ) {
        setError(err.message);
      } else {
        setError(
          err instanceof Error && err.message
            ? err.message
            : "We couldn't complete that payment. Please try again.",
        );
      }
    }
  }

  if (!token) {
    return (
      <div className="mx-auto max-w-lg">
        <Alert
          tone="danger"
          title="This checkout link is incomplete"
          actions={
            <Button size="sm" asChild>
              <Link href="/pricing">Back to pricing</Link>
            </Button>
          }
        >
          Start the upgrade again from the pricing page.
        </Alert>
      </div>
    );
  }

  return (
    <>
      <div className="mb-8 sm:mb-10">
        <Heading as="h1" size="xl">
          Complete your subscription
        </Heading>
        {/* The demo disclosure: unmissable if you read the page, but a line of
            text rather than a banner that makes the whole checkout look fake. */}
        <Text size="sm" tone="muted" className="mt-1.5">
          This is a simulated checkout — no real payment is processed and no
          card details are stored.
        </Text>
      </div>

      {/* Summary first on mobile (you should know what you are buying before
          you are asked to pay for it), beside the form from lg up. */}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_21rem] lg:gap-8">
        <section
          aria-labelledby="payment-details-heading"
          className="order-2 rounded-card border border-border bg-surface p-6 shadow-e1 sm:p-8 lg:order-1"
        >
          <Heading as="h2" size="sm" id="payment-details-heading">
            Payment details
          </Heading>

          <form onSubmit={pay} className="mt-6 flex flex-col gap-5">
            <Field label="Card number" id="card-number">
              <Input
                name="cardNumber"
                inputMode="numeric"
                autoComplete="off"
                placeholder="0000 0000 0000 0000"
                value={cardNumber}
                onChange={(event) =>
                  setCardNumber(formatCardNumber(event.target.value))
                }
                leadingIcon={CreditCard}
                required
              />
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field label="Expiry" id="card-expiry">
                <Input
                  name="expiry"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="MM / YY"
                  value={expiry}
                  onChange={(event) =>
                    setExpiry(formatExpiry(event.target.value))
                  }
                />
              </Field>

              <Field label="CVC" id="card-cvc">
                <Input
                  name="cvc"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="123"
                  value={cvc}
                  onChange={(event) =>
                    setCvc(event.target.value.replace(/\D/g, "").slice(0, 4))
                  }
                />
              </Field>
            </div>

            <Field label="Cardholder name" id="card-name">
              <Input
                name="cardholder"
                autoComplete="off"
                placeholder="Name on card"
                value={cardholder}
                onChange={(event) => setCardholder(event.target.value)}
              />
            </Field>

            {declined && (
              <Alert tone="danger" title="Payment declined" announce="assertive">
                {declined}
              </Alert>
            )}

            {error && (
              <Alert tone="danger" onDismiss={() => setError(null)}>
                {error}
              </Alert>
            )}

            <div className="flex flex-col gap-3 pt-1">
              <Button
                type="submit"
                size="lg"
                fullWidth
                loading={busy}
                loadingLabel="Processing your payment"
                leadingIcon={Lock}
              >
                Pay {PRO_PRICE_AMOUNT}
              </Button>

              <Text size="sm" tone="subtle" className="text-center">
                Demo checkout · No real charge
              </Text>

              {/* Distinct from the header's "Back to pricing", which is plain
                  chrome: abandoning from *here* carries ?checkout=cancelled,
                  which is what makes /pricing say "you have not been charged".
                  Someone backing out of a payment deserves that sentence. */}
              <Text size="sm" tone="subtle" className="text-center">
                <Link
                  href="/pricing?checkout=cancelled"
                  className="rounded-chip underline underline-offset-4 transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  Cancel
                </Link>{" "}
                and return to plans
              </Text>
            </div>
          </form>

          <DemoCards onUse={setCardNumber} />
        </section>

        <OrderSummary />
      </div>
    </>
  );
}

/**
 * The fixture cards, as a developer affordance.
 *
 * Deliberately below the pay button and visually quieter than the form: these
 * are how you *drive* the demo, not how you pay. Only the card number decides
 * the outcome, which is why nothing here touches the other fields.
 */
function DemoCards({ onUse }: { onUse: (card: string) => void }) {
  const cards = [
    { label: "Payment succeeds", number: SUCCESS_CARD, tone: "success" as const },
    { label: "Insufficient funds", number: DECLINE_CARD, tone: "danger" as const },
  ];

  return (
    <div className="mt-8 border-t border-border pt-5">
      <Text size="sm" tone="muted" className="font-semibold">
        Demo test cards
      </Text>
      <ul className="mt-3 flex flex-col gap-2">
        {cards.map((card) => (
          <li
            key={card.number}
            className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-panel bg-canvas-subtle px-3 py-2"
          >
            <span className="flex min-w-0 items-center gap-2.5">
              <span
                aria-hidden="true"
                className={
                  card.tone === "success"
                    ? "h-1.5 w-1.5 shrink-0 rounded-full bg-success"
                    : "h-1.5 w-1.5 shrink-0 rounded-full bg-danger"
                }
              />
              <code className="font-mono text-sm text-fg">{card.number}</code>
              <Text as="span" size="sm" tone="subtle" className="hidden sm:inline">
                {card.label}
              </Text>
            </span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => onUse(card.number)}
            >
              Use
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * What is being bought, from the shared plan data rather than a second copy of
 * the feature list. Sticky on desktop so it stays beside the form on a short
 * viewport; a plain block on mobile, where it leads.
 */
function OrderSummary() {
  const plan = planById("pro");

  return (
    <aside
      aria-labelledby="order-summary-heading"
      className="order-1 rounded-card border border-border bg-surface p-6 shadow-e1 lg:sticky lg:top-8 lg:order-2"
    >
      <Heading as="h2" size="sm" id="order-summary-heading">
        Order summary
      </Heading>

      <div className="mt-5 flex items-baseline justify-between gap-3">
        <Text className="font-semibold">{PAID_PLAN_NAME}</Text>
        <Text className="font-semibold tabular-nums">{PRO_PRICE_AMOUNT}</Text>
      </div>
      <Text size="sm" tone="subtle" className="mt-0.5">
        Billed {PRO_PRICE_PERIOD}
      </Text>

      <ul className="mt-5 flex flex-col gap-2.5">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5">
            <Icon
              icon={Check}
              size="xs"
              className="mt-1 shrink-0 text-success-fg"
            />
            <Text as="span" size="sm" tone="muted">
              {feature}
            </Text>
          </li>
        ))}
      </ul>

      <div className="mt-6 flex items-baseline justify-between gap-3 border-t border-border pt-4">
        <Text size="sm" tone="muted">
          Subtotal
        </Text>
        <Text size="sm" className="tabular-nums">
          {PRO_PRICE_AMOUNT}
        </Text>
      </div>
      <div className="mt-2 flex items-baseline justify-between gap-3">
        <Text className="font-semibold">Total</Text>
        <span className="text-right">
          <Text as="span" className="font-semibold tabular-nums">
            {PRO_PRICE_AMOUNT}
          </Text>
          <Text as="span" size="sm" tone="subtle">
            {" "}
            / month
          </Text>
        </span>
      </div>

      <Text size="sm" tone="subtle" className="mt-5">
        Cancel any time from your profile.
      </Text>
    </aside>
  );
}

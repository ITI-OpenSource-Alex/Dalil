/**
 * The two plans, in one place.
 *
 * This data used to live as a `TIERS` const inside
 * components/marketing/pricing.tsx, which was fine while the landing page was
 * the only surface that described the paid tier. GOA-039 adds a second one
 * (/pricing) that has to say exactly the same thing — and a product where the
 * marketing page and the checkout page disagree about what $20 buys is a
 * support ticket waiting to happen.
 *
 * Deliberately plain data: no JSX, no "use client", no imports. Both a Server
 * Component (the marketing section) and a client island (the /pricing plan
 * grid) read it, and the unit tests import it without a DOM.
 *
 * The price string is presentational only -- billing is simulated for this
 * project, so nothing is ever charged against it. It exists so the two pricing
 * surfaces and the checkout page all quote the same number.
 */

export type PlanId = "free" | "pro";

export interface PricingPlan {
  id: PlanId;
  name: string;
  /** One sentence on who the plan is for. */
  tagline: string;
  /** Formatted for display, e.g. "$20". Not used for any calculation. */
  price: string;
  /** Billing period, e.g. "per month". */
  period: string;
  features: string[];
  /** Emphasised card. Exactly one plan should carry this. */
  featured: boolean;
  /**
   * Where an anonymous visitor goes. Signed-in visitors get a tier-aware
   * action instead — see components/pricing/plan-grid.tsx.
   */
  signedOutCta: { label: string; href: string };
  /** Reassurance line under the action, where the hesitation actually is. */
  note: string;
}

/** The tier a paid subscriber is on, for mapping a user to a plan. */
export const PAID_PLAN_ID: PlanId = "pro";

/** Display name for the paid tier, used in copy across the app. */
export const PAID_PLAN_NAME = "Dalil Pro";

/** "$20 / month" -- the paid price as a sentence, for inline copy. */
export const PRO_PRICE_LABEL = "$20 / month";

/**
 * The same price split for checkout, where an amount and its period are laid
 * out as separate pieces (line item, total, pay button) rather than read as a
 * phrase. Two decimal places because that is how money is written on a
 * receipt; `PricingPlan.price` stays "$20" because that is how it is *sold*.
 */
export const PRO_PRICE_AMOUNT = "$20.00";
export const PRO_PRICE_PERIOD = "per month";

export const PRICING_PLANS: readonly PricingPlan[] = [
  {
    id: "free",
    name: "Free",
    tagline:
      "Everything you need to find a programme and plan the application.",
    price: "$0",
    period: "forever",
    features: [
      "AI opportunity matching with confidence scores",
      "Personalised application checklists",
      "Unlimited chat with Dalil",
      "CV upload and profile extraction",
    ],
    featured: false,
    signedOutCta: { label: "Get started free", href: "/register" },
    note: "No credit card required.",
  },
  {
    id: "pro",
    name: PAID_PLAN_NAME,
    tagline: "Full IELTS preparation with AI feedback across every skill.",
    price: "$20",
    period: "per month",
    features: [
      "Everything in Free",
      "Full IELTS exam simulations, all four skills",
      "Speaking practice with live transcription",
      "Writing evaluation with inline corrections",
      "CV review and rewrite suggestions",
    ],
    featured: true,
    // `next` survives the register → login → app hop, so someone who came
    // here to buy is returned here rather than dropped on /chat.
    signedOutCta: { label: "Start with Pro", href: "/register?next=/pricing" },
    note: "Cancel any time. No card required to try the free tier first.",
  },
] as const;

export function planById(id: PlanId): PricingPlan {
  const plan = PRICING_PLANS.find((candidate) => candidate.id === id);
  // Unreachable for the union above, but a lookup that can return undefined
  // would push a null check onto every call site for no reason.
  if (!plan) throw new Error(`Unknown pricing plan: ${id}`);
  return plan;
}

/** The plan a subscription tier corresponds to. */
export function planForTier(tier: "free" | "paid"): PricingPlan {
  return planById(tier === "paid" ? "pro" : "free");
}

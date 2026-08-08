/**
 * Billing, as the browser sees it (GOA-039).
 *
 * This project uses a self-contained demo payment rather than a payment
 * provider: the checkout page is served by this app, and the outcome is
 * decided server-side from a table of demo card numbers. There is no provider
 * SDK here, no publishable key, and no card data in transit to anyone but our
 * own backend — the numbers involved are fixtures, not instruments.
 *
 * Reached through the Gateway, not a service port and not a Next.js route
 * handler (this app has none): the Gateway owns JWT validation, rate limiting
 * and correlation IDs. Same reasoning as profile-api.ts / exam-api.ts
 * (BUG-046).
 *
 * What deliberately did NOT change when the provider went away: the upgrade is
 * still granted by the backend and never by this code, and /billing/success
 * still re-reads GET /api/profile instead of believing the redirect that
 * brought it there.
 */

import { dedupe } from "@/lib/request-dedupe";
import { throwForResponse } from "@/lib/subscription";

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080"}/api`;

/**
 * Off by default. The billing routes exist only where the User service runs
 * with BILLING_MODE=demo, and an Upgrade button that always 404s is worse than
 * one that says the feature is coming.
 *
 * Read inside the function rather than at module scope so tests (and a
 * server/client boundary crossing) see the current value.
 */
export function billingEnabled(): boolean {
  return process.env.NEXT_PUBLIC_BILLING_ENABLED === "true";
}

/** The endpoint is not deployed, or the Gateway could not be reached. */
export class BillingUnavailableError extends Error {
  constructor(message?: string) {
    super(
      message ??
        "Upgrades aren't available just yet. Please try again a little later.",
    );
    this.name = "BillingUnavailableError";
  }
}

/** The session is gone; the user has to sign in again before upgrading. */
export class BillingAuthError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again to continue.");
    this.name = "BillingAuthError";
  }
}

/**
 * The backend refused for a reason worth repeating verbatim — the account
 * already has the plan, the checkout has expired, the plan is not paid.
 *
 * The already-paid case is reachable in an ordinary way: upgrade in one tab
 * and a second tab still showing Free will happily offer Upgrade again.
 */
export class BillingConflictError extends Error {
  constructor(message?: string) {
    super(message || "That billing action could not be completed.");
    this.name = "BillingConflictError";
  }
}

export function isBillingUnavailableError(
  error: unknown,
): error is BillingUnavailableError {
  return error instanceof BillingUnavailableError;
}

export function isBillingAuthError(error: unknown): error is BillingAuthError {
  return error instanceof BillingAuthError;
}

export function isBillingConflictError(
  error: unknown,
): error is BillingConflictError {
  return error instanceof BillingConflictError;
}

/**
 * Pulls the human-readable sentence out of a backend error body.
 *
 * Both error shapes in this system carry it under `message` — the Gateway
 * sends fiber.Map{"message": ...} and the User service sends Nest's default
 * exception filter, whose class-validator variant makes it a string[]. Without
 * this the UI prints the whole JSON envelope at the user.
 */
async function backendMessage(response: Response): Promise<string | null> {
  const raw = await response.text().catch(() => "");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { message?: unknown };
    if (Array.isArray(parsed.message)) return parsed.message.join(" ");
    if (typeof parsed.message === "string") return parsed.message;
  } catch {
    // Not JSON -- leave it to the caller's fallback.
  }
  return null;
}

async function postBilling<T>(
  path: string,
  body: Record<string, unknown> = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // Network-level failure: DNS, offline, CORS preflight refused. From the
    // user's point of view this is indistinguishable from "not deployed".
    throw new BillingUnavailableError();
  }

  if (response.status === 401) throw new BillingAuthError();

  // 404 is ambiguous. A route that is not registered on the Gateway means
  // "not available yet"; Fiber answers that with no `message` field. A 404
  // that carries a message came from the domain and is worth showing.
  if (response.status === 404) {
    const message = await backendMessage(response.clone());
    if (message) throw new BillingConflictError(message);
    throw new BillingUnavailableError();
  }

  if ([501, 502, 503].includes(response.status)) {
    throw new BillingUnavailableError();
  }

  if (response.status === 400 || response.status === 409) {
    throw new BillingConflictError(
      (await backendMessage(response.clone())) ?? undefined,
    );
  }

  if (!response.ok) {
    // Prefer the backend's own sentence over its JSON envelope. `clone()` so
    // the original body is still unread for throwForResponse below, which
    // keeps the existing taxonomy (a paid-tier 403 stays a
    // SubscriptionRequiredError) rather than inventing a second one.
    const message = await backendMessage(response.clone());
    if (message) throw new Error(message);
    await throwForResponse(response);
  }

  return (await response.json().catch(() => null)) as T;
}

export interface BillingRedirect {
  /** An in-app URL: the demo checkout page this application serves. */
  url: string;
}

/**
 * Only our own origin is accepted as a checkout destination.
 *
 * The URL comes from our own backend, so this is not the primary defence — but
 * "our backend told us to" is exactly the reasoning behind every open redirect
 * that ever shipped. With the payment page now served by this app rather than
 * a provider, the correct destination set is precisely one origin: this one.
 */
function isSameOriginUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  if (typeof window === "undefined") return false;
  try {
    return new URL(value, window.location.origin).origin === window.location.origin;
  } catch {
    return false;
  }
}

/**
 * POST /api/billing/create-checkout
 *
 * The user id is deliberately not sent: the Gateway derives it from the JWT,
 * so a caller cannot start a checkout for somebody else's account. The return
 * URLs are sent because the frontend owns its own routes; the Gateway
 * validates them against an allow-list rather than trusting them.
 *
 * Deduped: a second click while the first request is in flight gets the same
 * promise instead of opening a second checkout session. The entry clears as
 * soon as it settles, so a genuine retry after a failure still makes a real
 * request.
 */
export async function createCheckoutSession(): Promise<BillingRedirect> {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return dedupe(`POST ${API_BASE}/billing/create-checkout`, async () => {
    const data = await postBilling<{ url?: unknown }>(
      "/billing/create-checkout",
      {
        successUrl: `${origin}/billing/success`,
        cancelUrl: `${origin}/pricing?checkout=cancelled`,
      },
    );

    if (!isSameOriginUrl(data?.url)) {
      throw new Error("Billing returned an unexpected response. Please try again.");
    }
    return { url: data.url };
  });
}

export type DemoPaymentResult =
  | { status: "succeeded"; redirectUrl: string }
  | { status: "declined"; message: string };

/**
 * POST /api/billing/demo/confirm — settles the demo payment.
 *
 * A declined card comes back as a 200 with `status: "declined"`, the way a
 * hosted payment page would render a decline rather than a transport error.
 * Only a spent or expired checkout is a 4xx.
 *
 * The card number is a fixture matched against a server-side table; it is not
 * a payment instrument and no real card should ever be typed here.
 */
export async function confirmDemoPayment(
  token: string,
  cardNumber: string,
): Promise<DemoPaymentResult> {
  return dedupe(`POST ${API_BASE}/billing/demo/confirm`, async () => {
    const data = await postBilling<DemoPaymentResult>("/billing/demo/confirm", {
      token,
      cardNumber,
    });

    if (data?.status === "succeeded") {
      if (!isSameOriginUrl(data.redirectUrl)) {
        throw new Error("Billing returned an unexpected response.");
      }
      return data;
    }
    if (data?.status === "declined") return data;

    throw new Error("Billing returned an unexpected response. Please try again.");
  });
}

/**
 * POST /api/billing/cancel — ends the subscription.
 *
 * No payload: which subscription is being cancelled follows from the session.
 */
export async function cancelSubscription(): Promise<{
  subscriptionTier: "free" | "paid";
}> {
  return dedupe(`POST ${API_BASE}/billing/cancel`, () =>
    postBilling<{ subscriptionTier: "free" | "paid" }>("/billing/cancel"),
  );
}

/**
 * Leaves the current page for the checkout.
 *
 * A full document navigation rather than router.push: the destination reads
 * the freshly-written subscription state, and a client-side transition would
 * carry this page's already-stale copy of the profile into it.
 */
export function redirectTo(url: string): void {
  window.location.assign(url);
}

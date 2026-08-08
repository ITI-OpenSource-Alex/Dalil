import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  billingEnabled,
  cancelSubscription,
  confirmDemoPayment,
  createCheckoutSession,
  isBillingAuthError,
  isBillingConflictError,
  isBillingUnavailableError,
  redirectTo,
} from "@/lib/billing-api";
import { isSubscriptionRequiredError } from "@/lib/subscription";

const ORIGIN = "http://localhost:3000";
const CHECKOUT_URL = `${ORIGIN}/billing/demo-checkout?session=abc123`;
const TOKEN = "a".repeat(64);
const SUCCESS_CARD = "4242424242424242";

function ok(body: unknown) {
  const response = {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
    clone: () => response,
  };
  return response as unknown as Response;
}

function fail(status: number, body: string) {
  const response = {
    ok: false,
    status,
    text: async () => body,
    json: async () => JSON.parse(body),
    // The implementation clones before reading, so the original body stays
    // available to the existing throwForResponse fallback.
    clone: () => response,
  };
  return response as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal("location", { origin: ORIGIN, assign: vi.fn() });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("createCheckoutSession", () => {
  it("posts to the Gateway with the session cookie and returns the checkout URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ url: CHECKOUT_URL }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createCheckoutSession()).resolves.toEqual({
      url: CHECKOUT_URL,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/billing/create-checkout"),
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("sends return URLs the frontend actually owns", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ url: CHECKOUT_URL }));
    vi.stubGlobal("fetch", fetchMock);

    await createCheckoutSession();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.successUrl).toBe(`${ORIGIN}/billing/success`);
    expect(body.cancelUrl).toBe(`${ORIGIN}/pricing?checkout=cancelled`);
  });

  it("never sends a user id or a tier -- the Gateway derives identity from the JWT", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ url: CHECKOUT_URL }));
    vi.stubGlobal("fetch", fetchMock);

    await createCheckoutSession();

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).not.toHaveProperty("userId");
    expect(body).not.toHaveProperty("tier");
    expect(body).not.toHaveProperty("subscriptionTier");
  });

  it("collapses a double click into one checkout session", async () => {
    // Two clicks landing before the first response would otherwise open two
    // sessions, and the demo checkout page would hold a token that is not the
    // one the user is about to submit.
    let resolveFetch: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(pending);
    vi.stubGlobal("fetch", fetchMock);

    const first = createCheckoutSession();
    const second = createCheckoutSession();
    resolveFetch(ok({ url: CHECKOUT_URL }));

    await expect(first).resolves.toEqual({ url: CHECKOUT_URL });
    await expect(second).resolves.toEqual({ url: CHECKOUT_URL });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("still makes a real request on a retry after the first settles", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok({ url: CHECKOUT_URL }));
    vi.stubGlobal("fetch", fetchMock);

    await createCheckoutSession();
    await createCheckoutSession();

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("reports a bare 404 as billing not being deployed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fail(404, "Not Found")));

    await expect(createCheckoutSession()).rejects.toSatisfy(
      isBillingUnavailableError,
    );
  });

  it.each([501, 502, 503])("reports a %i as unavailable", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(fail(status, "upstream down")),
    );
    await expect(createCheckoutSession()).rejects.toSatisfy(
      isBillingUnavailableError,
    );
  });

  it("reports a network failure as unavailable rather than leaking the fetch error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(createCheckoutSession()).rejects.toSatisfy(
      isBillingUnavailableError,
    );
  });

  it("reports an expired session distinctly, so the UI can offer sign-in", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(fail(401, "unauthorized")));

    await expect(createCheckoutSession()).rejects.toSatisfy(isBillingAuthError);
  });

  it("reports an already-paid account as a conflict, not a raw JSON blob", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fail(
          409,
          JSON.stringify({
            message: "This account already has Dalil Pro",
            error: "Conflict",
            statusCode: 409,
          }),
        ),
      ),
    );

    const error = await createCheckoutSession().catch((err: unknown) => err);
    expect(isBillingConflictError(error)).toBe(true);
    expect((error as Error).message).toBe("This account already has Dalil Pro");
    expect((error as Error).message).not.toContain("statusCode");
  });

  it("keeps the paid-tier 403 taxonomy intact", async () => {
    // Reuses lib/subscription.ts rather than inventing a second error system.
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          fail(403, JSON.stringify({ error: "subscription_required" })),
        ),
    );

    await expect(createCheckoutSession()).rejects.toSatisfy(
      isSubscriptionRequiredError,
    );
  });

  it("refuses a checkout URL that is not on our own origin", async () => {
    // Our own backend supplies this URL, but "the backend said so" is the
    // reasoning behind every open redirect that ever shipped. The payment page
    // is served by this app, so exactly one origin is correct.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(ok({ url: "https://evil.test/demo-checkout" })),
    );

    await expect(createCheckoutSession()).rejects.toThrow(/unexpected response/i);
  });

  it("refuses a response with no url at all", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({})));

    await expect(createCheckoutSession()).rejects.toThrow(/unexpected response/i);
  });
});

describe("confirmDemoPayment", () => {
  it("returns the success outcome and its redirect", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ok({ status: "succeeded", redirectUrl: `${ORIGIN}/billing/success` }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(confirmDemoPayment(TOKEN, SUCCESS_CARD)).resolves.toEqual({
      status: "succeeded",
      redirectUrl: `${ORIGIN}/billing/success`,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/billing/demo/confirm"),
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("sends only the token and the card field", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(ok({ status: "declined", message: "no" }));
    vi.stubGlobal("fetch", fetchMock);

    await confirmDemoPayment(TOKEN, SUCCESS_CARD);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({ token: TOKEN, cardNumber: SUCCESS_CARD });
  });

  it("returns a decline as a normal outcome, not an exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        ok({
          status: "declined",
          message: "Your card has insufficient funds.",
        }),
      ),
    );

    await expect(confirmDemoPayment(TOKEN, "4000000000009995")).resolves.toEqual(
      { status: "declined", message: "Your card has insufficient funds." },
    );
  });

  it("surfaces a spent or expired checkout as a conflict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fail(
          400,
          JSON.stringify({
            message:
              "This checkout has expired or has already been used. Please start again.",
          }),
        ),
      ),
    );

    const error = await confirmDemoPayment(TOKEN, SUCCESS_CARD).catch(
      (err: unknown) => err,
    );
    expect(isBillingConflictError(error)).toBe(true);
    expect((error as Error).message).toMatch(/already been used/);
  });

  it("refuses a success redirect that points off-origin", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          ok({ status: "succeeded", redirectUrl: "https://evil.test/" }),
        ),
    );

    await expect(confirmDemoPayment(TOKEN, SUCCESS_CARD)).rejects.toThrow(
      /unexpected response/i,
    );
  });

  it("rejects an unrecognised outcome shape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({ status: "maybe" })));

    await expect(confirmDemoPayment(TOKEN, SUCCESS_CARD)).rejects.toThrow(
      /unexpected response/i,
    );
  });

  it("collapses a double submit into one confirmation", async () => {
    // The token is single-use server-side; a second in-flight request would
    // simply fail, but not sending it at all is the better experience.
    let resolveFetch: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(pending);
    vi.stubGlobal("fetch", fetchMock);

    const first = confirmDemoPayment(TOKEN, SUCCESS_CARD);
    const second = confirmDemoPayment(TOKEN, SUCCESS_CARD);
    resolveFetch(ok({ status: "declined", message: "no" }));

    await Promise.all([first, second]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("cancelSubscription", () => {
  it("sends no payload at all", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(ok({ subscriptionTier: "free" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(cancelSubscription()).resolves.toEqual({
      subscriptionTier: "free",
    });

    // Whose subscription is cancelled follows from the session cookie, so
    // there is no field a caller could use to name a victim.
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toEqual({});
  });

  it("surfaces the backend's reason when the plan is not paid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        fail(409, JSON.stringify({ message: "This account is not on a paid plan" })),
      ),
    );

    const error = await cancelSubscription().catch((err: unknown) => err);
    expect(isBillingConflictError(error)).toBe(true);
    expect((error as Error).message).toBe("This account is not on a paid plan");
  });
});

describe("redirectTo", () => {
  it("leaves the page with a full document navigation", () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { origin: ORIGIN, assign });

    redirectTo(CHECKOUT_URL);

    expect(assign).toHaveBeenCalledWith(CHECKOUT_URL);
  });
});

describe("billingEnabled", () => {
  it("is off unless explicitly turned on", () => {
    vi.stubEnv("NEXT_PUBLIC_BILLING_ENABLED", "");
    expect(billingEnabled()).toBe(false);

    vi.stubEnv("NEXT_PUBLIC_BILLING_ENABLED", "false");
    expect(billingEnabled()).toBe(false);

    vi.stubEnv("NEXT_PUBLIC_BILLING_ENABLED", "1");
    expect(billingEnabled()).toBe(false);
  });

  it('is on for exactly "true"', () => {
    vi.stubEnv("NEXT_PUBLIC_BILLING_ENABLED", "true");
    expect(billingEnabled()).toBe(true);
  });
});

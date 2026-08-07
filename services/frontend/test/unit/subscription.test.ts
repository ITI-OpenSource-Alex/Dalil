import { describe, expect, it } from "vitest";
import {
  DEFAULT_UPGRADE_URL,
  isSubscriptionRequiredError,
  isSubscriptionRequiredMessage,
  paidFeatureCopy,
  subscriptionErrorFromAxios,
  throwForResponse,
} from "@/lib/subscription";

function response(status: number, body: string): Response {
  return {
    status,
    text: async () => body,
  } as unknown as Response;
}

describe("throwForResponse", () => {
  it("raises a SubscriptionRequiredError for the Gateway's paid-tier 403", async () => {
    // The exact body RequirePaid sends (gateway/middleware/subscription.go).
    const promise = throwForResponse(
      response(
        403,
        JSON.stringify({
          error: "subscription_required",
          upgradeUrl: "https://billing.example/upgrade",
        }),
      ),
      "exam",
    );

    await expect(promise).rejects.toSatisfy(isSubscriptionRequiredError);
    await promise.catch((err) => {
      expect(err.upgradeUrl).toBe("https://billing.example/upgrade");
      expect(err.feature).toBe("exam");
    });
  });

  it("falls back to the in-app upgrade route when the Gateway names none", async () => {
    await throwForResponse(
      response(403, JSON.stringify({ error: "subscription_required" })),
    ).catch((err) => {
      expect(err.upgradeUrl).toBe(DEFAULT_UPGRADE_URL);
    });
  });

  it("leaves an ordinary 403 as a plain Error", async () => {
    // A forbidden that is *not* the paywall — e.g. exam ownership — must not
    // be dressed up as an upgrade prompt.
    const promise = throwForResponse(
      response(403, JSON.stringify({ message: "not your session" })),
    );
    await expect(promise).rejects.toThrow(/not your session/);
    await expect(promise).rejects.not.toSatisfy(isSubscriptionRequiredError);
  });

  it("surfaces the backend message for any other status", async () => {
    await expect(throwForResponse(response(500, "upstream exploded"))).rejects.toThrow(
      /upstream exploded/,
    );
  });

  it("names the status when the body is empty", async () => {
    await expect(throwForResponse(response(502, ""))).rejects.toThrow(/502/);
  });
});

describe("subscriptionErrorFromAxios", () => {
  it("detects the paywall on an axios error", () => {
    const error = {
      response: {
        status: 403,
        data: { error: "subscription_required", upgradeUrl: "/pricing" },
      },
    };
    const result = subscriptionErrorFromAxios(error, "cv-review");
    expect(result).not.toBeNull();
    expect(result!.upgradeUrl).toBe("/pricing");
    expect(result!.feature).toBe("cv-review");
  });

  it("returns null for anything else", () => {
    expect(subscriptionErrorFromAxios(new Error("boom"))).toBeNull();
    expect(
      subscriptionErrorFromAxios({ response: { status: 403, data: {} } }),
    ).toBeNull();
    expect(
      subscriptionErrorFromAxios({ response: { status: 500, data: null } }),
    ).toBeNull();
  });
});

describe("isSubscriptionRequiredMessage", () => {
  it("matches the marker orchestration sends in the SSE error event", () => {
    expect(isSubscriptionRequiredMessage("subscription_required")).toBe(true);
    expect(isSubscriptionRequiredMessage(" Subscription_Required ")).toBe(true);
  });

  it("does not match a real error sentence", () => {
    expect(
      isSubscriptionRequiredMessage(
        "I'm sorry, but the Writing evaluation service is currently offline.",
      ),
    ).toBe(false);
    expect(isSubscriptionRequiredMessage(undefined)).toBe(false);
  });
});

describe("paidFeatureCopy", () => {
  it("gives every exam skill the same explanation", () => {
    // They are all gated by the one /api/exam group, so a candidate who
    // clicked Reading should not read a different story from one who clicked
    // Writing.
    expect(paidFeatureCopy("exam-reading")).toBe(paidFeatureCopy("exam"));
    expect(paidFeatureCopy("exam-writing")).toBe(paidFeatureCopy("exam"));
  });

  it("falls back to generic copy for an unnamed feature", () => {
    const copy = paidFeatureCopy(undefined);
    expect(copy.title).toMatch(/GOA Pro/);
    expect(copy.benefits.length).toBeGreaterThan(0);
  });
});

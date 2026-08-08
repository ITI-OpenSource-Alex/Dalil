import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PRICING_PLANS, planForTier } from "@/lib/pricing-plans";

const profileMock = vi.hoisted(() => ({ getMyProfile: vi.fn() }));
vi.mock("@/lib/profile-api", () => profileMock);

// There is no App Router around a Vitest render, so useSearchParams has no
// context to read. The query string is the input to the cancelled-checkout
// notice, so it is stubbed rather than avoided.
const searchMock = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchMock.params,
}));

const billingMock = vi.hoisted(() => ({
  billingEnabled: vi.fn(() => true),
  createCheckoutSession: vi.fn(),
  redirectTo: vi.fn(),
  isBillingUnavailableError: vi.fn(() => false),
  isBillingAuthError: vi.fn(() => false),
  isBillingConflictError: vi.fn(() => false),
}));
vi.mock("@/lib/billing-api", () => billingMock);

const { PricingPlans } = await import("@/components/pricing/plan-grid");

const FREE_USER = {
  id: "user-1",
  email: "student@example.com",
  subscriptionTier: "free" as const,
  isVerified: true,
  profile: null,
};

const PAID_USER = { ...FREE_USER, subscriptionTier: "paid" as const };

afterEach(() => {
  vi.clearAllMocks();
  billingMock.billingEnabled.mockReturnValue(true);
  billingMock.isBillingUnavailableError.mockReturnValue(false);
  billingMock.isBillingAuthError.mockReturnValue(false);
  billingMock.isBillingConflictError.mockReturnValue(false);
  searchMock.params = new URLSearchParams();
});

describe("pricing plan data", () => {
  it("describes exactly two plans, one of them featured", () => {
    expect(PRICING_PLANS).toHaveLength(2);
    expect(PRICING_PLANS.filter((plan) => plan.featured)).toHaveLength(1);
  });

  it("keeps Pro a superset of Free, as the copy claims", () => {
    const pro = planForTier("paid");
    expect(pro.features[0]).toBe("Everything in Free");
    expect(pro.features.length).toBeGreaterThan(
      planForTier("free").features.length,
    );
  });

  it("maps a subscription tier onto the right plan", () => {
    expect(planForTier("free").id).toBe("free");
    expect(planForTier("paid").id).toBe("pro");
  });
});

describe("/pricing — signed out", () => {
  it("renders both tiers with their prices and no profile request", () => {
    render(<PricingPlans signedIn={false} />);

    expect(screen.getByRole("heading", { name: "Free" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dalil Pro" })).toBeInTheDocument();
    expect(screen.getByText("$0")).toBeInTheDocument();
    expect(screen.getByText("$7")).toBeInTheDocument();

    // Nothing to fetch: there is no session to describe.
    expect(profileMock.getMyProfile).not.toHaveBeenCalled();
  });

  it("sends an anonymous visitor to registration, preserving where they were", () => {
    render(<PricingPlans signedIn={false} />);

    expect(screen.getByRole("link", { name: "Get started free" })).toHaveAttribute(
      "href",
      "/register",
    );
    expect(screen.getByRole("link", { name: /Start with Pro/ })).toHaveAttribute(
      "href",
      "/register?next=/pricing",
    );
  });
});

describe("/pricing — cancelled checkout", () => {
  it("reassures the visitor they were not charged", () => {
    // The checkout page's Cancel link brings them back here with this marker.
    searchMock.params = new URLSearchParams("checkout=cancelled");

    render(<PricingPlans signedIn={false} />);

    expect(screen.getByText("Payment cancelled")).toBeInTheDocument();
    expect(screen.getByText(/have not been charged/)).toBeInTheDocument();
  });

  it("says nothing about payment on an ordinary visit", () => {
    render(<PricingPlans signedIn={false} />);

    expect(screen.queryByText("Payment cancelled")).not.toBeInTheDocument();
  });
});

describe("/pricing — signed-in free user", () => {
  it("offers the upgrade and marks Free as the current plan", async () => {
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);

    render(<PricingPlans signedIn />);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Upgrade to Dalil Pro/ }),
      ).toBeEnabled(),
    );
    expect(screen.getByRole("button", { name: "Your current plan" })).toBeDisabled();
  });

  it("starts checkout and sends the browser to the checkout page", async () => {
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);
    billingMock.createCheckoutSession.mockResolvedValue({
      url: "http://localhost:3000/billing/demo-checkout?session=abc",
    });

    render(<PricingPlans signedIn />);
    const button = await screen.findByRole("button", {
      name: /Upgrade to Dalil Pro/,
    });
    await userEvent.click(button);

    await waitFor(() =>
      expect(billingMock.redirectTo).toHaveBeenCalledWith(
        "http://localhost:3000/billing/demo-checkout?session=abc",
      ),
    );
  });

  it("does not fire a second checkout while the first is in flight", async () => {
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);
    billingMock.createCheckoutSession.mockReturnValue(new Promise(() => {}));

    render(<PricingPlans signedIn />);
    const button = await screen.findByRole("button", {
      name: /Upgrade to Dalil Pro/,
    });
    await userEvent.click(button);
    await userEvent.click(button);

    expect(billingMock.createCheckoutSession).toHaveBeenCalledTimes(1);
  });

  it("shows a readable message when checkout fails, and stays usable", async () => {
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);
    billingMock.createCheckoutSession.mockRejectedValue(
      new Error("Card network unavailable"),
    );

    render(<PricingPlans signedIn />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Upgrade to Dalil Pro/ }),
    );

    expect(await screen.findByText("Card network unavailable")).toBeInTheDocument();
    // Recoverable: the button comes back rather than staying stuck busy.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Upgrade to Dalil Pro/ }),
      ).toBeEnabled(),
    );
  });

  it("tells an already-upgraded account it has Pro, and refetches the tier", async () => {
    // Pay in one tab and this tab still shows Free. The backend refuses the
    // second subscription with a 409; the page must explain that and correct
    // itself rather than showing a failure.
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);
    billingMock.isBillingConflictError.mockReturnValue(true);
    billingMock.createCheckoutSession.mockRejectedValue(
      new Error("This account already has Dalil Pro"),
    );

    render(<PricingPlans signedIn />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Upgrade to Dalil Pro/ }),
    );

    expect(
      await screen.findByText("This account already has Dalil Pro"),
    ).toBeInTheDocument();
    // The profile is re-read: once, on mount, and again after the conflict.
    await waitFor(() =>
      expect(profileMock.getMyProfile.mock.calls.length).toBeGreaterThan(1),
    );
  });

  it("does not offer a checkout that would 404 when billing is not deployed", async () => {
    billingMock.billingEnabled.mockReturnValue(false);
    profileMock.getMyProfile.mockResolvedValue(FREE_USER);

    render(<PricingPlans signedIn />);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Upgrades coming soon" }),
      ).toBeDisabled(),
    );
    expect(screen.getByText("Checkout isn't live yet")).toBeInTheDocument();
    expect(billingMock.createCheckoutSession).not.toHaveBeenCalled();
  });
});

describe("/pricing — signed-in paid user", () => {
  it("does not try to sell Pro to somebody who already has it", async () => {
    profileMock.getMyProfile.mockResolvedValue(PAID_USER);

    render(<PricingPlans signedIn />);

    await waitFor(() =>
      expect(
        screen.getByRole("link", { name: /Manage subscription/ }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: /Upgrade to Dalil Pro/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("You're on Dalil Pro")).toBeInTheDocument();
  });

  it("points a subscriber at the in-app manage page", async () => {
    profileMock.getMyProfile.mockResolvedValue(PAID_USER);

    render(<PricingPlans signedIn />);

    expect(
      await screen.findByRole("link", { name: /Manage subscription/ }),
    ).toHaveAttribute("href", "/billing/manage");
    // No payment provider means no outbound redirect to one.
    expect(billingMock.redirectTo).not.toHaveBeenCalled();
  });
});

describe("/pricing — identity still loading", () => {
  it("offers no tier-dependent action until the server has answered", () => {
    // Guessing Free would try to sell Pro to a subscriber; guessing Paid would
    // hide the only action a Free user came for.
    profileMock.getMyProfile.mockReturnValue(new Promise(() => {}));

    render(<PricingPlans signedIn />);

    expect(
      screen.getByRole("button", { name: "Upgrade to Dalil Pro" }),
    ).toBeDisabled();
  });
});

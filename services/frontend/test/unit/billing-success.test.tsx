import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

const profileMock = vi.hoisted(() => ({ getMyProfile: vi.fn() }));
vi.mock("@/lib/profile-api", () => profileMock);

const BillingSuccessPage = (
  await import("@/app/(app)/billing/success/page")
).default;

const FREE = {
  id: "user-1",
  email: "student@example.com",
  subscriptionTier: "free" as const,
  isVerified: true,
  profile: null,
};

const PAID = { ...FREE, subscriptionTier: "paid" as const };

/** Matches POLL_INTERVAL_MS / MAX_ATTEMPTS in the page. */
const INTERVAL = 1500;
const ATTEMPTS = 10;

/**
 * Fake timers, because the page's honest behaviour is to wait ~15 seconds
 * before admitting activation is slow — and a suite that actually waits that
 * long is a suite people stop running.
 */
beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

/** Lets the first (immediate) poll resolve. */
async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function advancePolls(count: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(INTERVAL * count);
  });
}

describe("/billing/success", () => {
  it("waits for the webhook rather than trusting the redirect", async () => {
    // The checkout has sent the browser here, but the tier has not flipped
    // yet. Nothing on this page may claim the subscription is active on the
    // strength of the redirect alone.
    profileMock.getMyProfile.mockResolvedValue(FREE);

    render(<BillingSuccessPage />);
    await settle();

    expect(screen.getByText(/Activating your subscription/)).toBeInTheDocument();
    expect(screen.queryByText(/subscription is active/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Take an IELTS exam/ }),
    ).not.toBeInTheDocument();
  });

  it("confirms once the profile reports the paid tier", async () => {
    // free -> free -> paid: the webhook lands on the third check.
    profileMock.getMyProfile
      .mockResolvedValueOnce(FREE)
      .mockResolvedValueOnce(FREE)
      .mockResolvedValue(PAID);

    render(<BillingSuccessPage />);
    await settle();
    await advancePolls(2);

    expect(screen.getByText(/Your subscription is active/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Take an IELTS exam/ }),
    ).toHaveAttribute("href", "/exam");
  });

  it("stops polling once it has an answer", async () => {
    profileMock.getMyProfile.mockResolvedValue(PAID);

    render(<BillingSuccessPage />);
    await settle();

    const callsAtSuccess = profileMock.getMyProfile.mock.calls.length;
    await advancePolls(5);

    expect(profileMock.getMyProfile.mock.calls.length).toBe(callsAtSuccess);
  });

  it("polls a bounded number of times, then stops", async () => {
    profileMock.getMyProfile.mockResolvedValue(FREE);

    render(<BillingSuccessPage />);
    await settle();
    await advancePolls(ATTEMPTS + 5);

    // A permanent polling loop against the Gateway would keep climbing.
    expect(profileMock.getMyProfile.mock.calls.length).toBe(ATTEMPTS);
  });

  it("never claims failure when activation is slow, and offers a retry", async () => {
    // The user's money is gone. "Payment failed" would be both wrong and
    // alarming; the honest answer is that confirmation is still in flight.
    profileMock.getMyProfile.mockResolvedValue(FREE);

    render(<BillingSuccessPage />);
    await settle();
    await advancePolls(ATTEMPTS);

    expect(screen.getByText("Still activating")).toBeInTheDocument();
    expect(screen.queryByText(/payment failed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/subscription is active/)).not.toBeInTheDocument();

    const before = profileMock.getMyProfile.mock.calls.length;
    await act(async () => {
      screen.getByRole("button", { name: /Check again/ }).click();
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(profileMock.getMyProfile.mock.calls.length).toBeGreaterThan(before);
  });

  it("keeps polling through a transient profile failure instead of giving up", async () => {
    profileMock.getMyProfile
      .mockRejectedValueOnce(new Error("Gateway timeout"))
      .mockResolvedValue(PAID);

    render(<BillingSuccessPage />);
    await settle();
    await advancePolls(2);

    expect(screen.getByText(/Your subscription is active/)).toBeInTheDocument();
  });
});

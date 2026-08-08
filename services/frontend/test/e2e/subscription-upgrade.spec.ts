import { test, expect, Page } from "./fixtures/auth";

/**
 * GOA-039 — the upgrade journey as the browser experiences it, with the
 * Gateway mocked.
 *
 * There is no payment provider in this flow at all: the checkout page is served
 * by this application and the outcome is decided by the backend. These specs
 * therefore own the browser's half — the modal that appears, where it sends the
 * user, what /pricing offers each kind of visitor, what the client sends, the
 * declined and cancelled paths, and the confirmation page's refusal to declare
 * success until the profile says so.
 *
 * The other half — the real payment lifecycle against a live stack — is in
 * tests/e2e/test_goa_039_subscription_lifecycle.py. See the note at the bottom.
 */

// Same-origin note as dashboard.spec.ts: the frontend runs on :3000 and calls
// the Gateway on :8080, so mocked responses need CORS headers.
const GATEWAY = "http://localhost:8080";

function withCors(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Origin": "http://localhost:3000",
      "Access-Control-Allow-Credentials": "true",
    },
    body: JSON.stringify(body),
  };
}

const FREE_PROFILE = {
  id: "user-1",
  email: "student@example.com",
  subscriptionTier: "free",
  isVerified: true,
  profile: {
    userId: "user-1",
    degreeLevel: "Bachelors",
    gpa: 3.4,
    ieltsScore: 6.5,
    targetCountries: ["Germany"],
    fieldOfStudy: "Computer Science",
    ects: 180,
    workExperienceYears: 1,
    extracurricularsScore: 4,
    gpaScale: "4.0",
  },
};

const PAID_PROFILE = { ...FREE_PROFILE, subscriptionTier: "paid" };

const DEMO_TOKEN = "a".repeat(64);
const CHECKOUT_URL = `http://localhost:3000/billing/demo-checkout?session=${DEMO_TOKEN}`;

async function mockProfile(page: Page, profile: unknown) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(withCors(profile)),
  );
}

test.describe("Upgrade prompt", () => {
  test("a free user who reaches for a paid feature is told what Pro gives them, and sent to /pricing", async ({
    page,
  }) => {
    await mockProfile(page, FREE_PROFILE);
    // The exam landing page also reads progress; a free account is refused it.
    await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
      route.fulfill(
        withCors({ error: "subscription_required", upgradeUrl: "/pricing" }, 403),
      ),
    );

    await page.goto("/exam");

    // The "Pro" chip on each card only renders once the profile has resolved
    // AND reports a free tier. Clicking before that gets the page's "profile
    // still loading" guard rather than the paywall -- deliberate behaviour
    // there, and a race here.
    await expect(page.getByText("Pro", { exact: true }).first()).toBeVisible();

    // Any of the skill cards opens the same gate.
    await page.getByRole("button", { name: "Take Exam" }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Dalil Pro");
    // The criterion is "lists what they get" — the benefit list, not just a
    // title.
    await expect(dialog.getByText(/Band scores/i)).toBeVisible();

    await dialog.getByRole("link", { name: /Upgrade to Dalil Pro/ }).click();
    await expect(page).toHaveURL(/\/pricing$/);
  });
});

test.describe("/pricing", () => {
  test("renders both tiers for a signed-out visitor and points them at registration", async ({
    page,
  }) => {
    await page.context().clearCookies({ name: "access_token" });

    await page.goto("/pricing");

    await expect(page.getByRole("heading", { name: "Free", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dalil Pro" })).toBeVisible();
    // exact: the FAQ further down the page also mentions the price in prose.
    await expect(page.getByText("$0", { exact: true })).toBeVisible();
    await expect(page.getByText("$7", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Start with Pro/ }),
    ).toHaveAttribute("href", "/register?next=/pricing");
  });

  test("a signed-in free user gets a working upgrade action and reaches the checkout page", async ({
    page,
  }) => {
    await mockProfile(page, FREE_PROFILE);

    let checkoutBody: Record<string, unknown> | null = null;
    await page.route(`${GATEWAY}/api/billing/create-checkout`, (route) => {
      checkoutBody = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill(withCors({ url: CHECKOUT_URL }));
    });

    await page.goto("/pricing");

    // NEXT_PUBLIC_BILLING_ENABLED is inlined into the client bundle, so it is
    // a property of the *server process* Playwright is talking to. If a dev
    // server started by hand is being reused (reuseExistingServer is on
    // locally), it will not have the flag from playwright.config.ts and this
    // button renders disabled -- which otherwise shows up as an unexplained
    // 30s click timeout. Say so instead.
    await expect(
      page.getByRole("button", { name: "Upgrades coming soon" }),
      "billing is disabled on the server under test: stop any hand-started " +
        "`npm run dev` on :3000 so Playwright starts its own with " +
        "NEXT_PUBLIC_BILLING_ENABLED=true",
    ).toHaveCount(0);

    await page.getByRole("button", { name: /Upgrade to Dalil Pro/ }).click();

    // The checkout page is served by this app, so the browser stays on our own
    // origin -- there is no third party in the flow at all.
    await page.waitForURL(/\/billing\/demo-checkout/);
    expect(checkoutBody).toBeTruthy();
    expect(checkoutBody!.successUrl).toContain("/billing/success");
    expect(checkoutBody!.cancelUrl).toContain("/pricing?checkout=cancelled");

    await expect(page.getByText(/simulated checkout/i)).toBeVisible();
  });

  test("the demo checkout upgrades on the success card", async ({ page }) => {
    await mockProfile(page, FREE_PROFILE);

    let confirmBody: Record<string, unknown> | null = null;
    await page.route(`${GATEWAY}/api/billing/demo/confirm`, (route) => {
      confirmBody = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill(
        withCors({
          status: "succeeded",
          redirectUrl: "http://localhost:3000/billing/success",
        }),
      );
    });

    await page.goto(`/billing/demo-checkout?session=${DEMO_TOKEN}`);
    await page.getByRole("button", { name: /^Pay/ }).click();

    await page.waitForURL(/\/billing\/success/);
    // The token identifies the checkout; the card decides the outcome. Neither
    // a user id nor a tier is sent -- the backend owns both.
    expect(confirmBody).toEqual({
      token: DEMO_TOKEN,
      cardNumber: "4242 4242 4242 4242",
    });
  });

  test("the demo checkout shows a decline and stays put", async ({ page }) => {
    await mockProfile(page, FREE_PROFILE);
    await page.route(`${GATEWAY}/api/billing/demo/confirm`, (route) =>
      route.fulfill(
        withCors({
          status: "declined",
          message: "Your card has insufficient funds.",
        }),
      ),
    );

    await page.goto(`/billing/demo-checkout?session=${DEMO_TOKEN}`);
    await page.getByRole("button", { name: "Use" }).nth(1).click();
    await page.getByRole("button", { name: /^Pay/ }).click();

    // Scoped to the decline alert on two counts: the test-card hints on the
    // same page also say "insufficient funds", and Next.js ships its own
    // empty role="alert" route announcer.
    const declineAlert = page
      .getByRole("alert")
      .filter({ hasText: "Payment declined" });
    await expect(declineAlert).toBeVisible();
    await expect(declineAlert).toContainText("Your card has insufficient funds.");
    // Still on the checkout page, and still able to retry.
    await expect(page).toHaveURL(/\/billing\/demo-checkout/);
    await expect(page.getByRole("button", { name: /^Pay/ })).toBeEnabled();
  });

  test("cancelling the demo checkout returns the user to pricing", async ({
    page,
  }) => {
    await mockProfile(page, FREE_PROFILE);

    await page.goto(`/billing/demo-checkout?session=${DEMO_TOKEN}`);
    await page.getByRole("link", { name: "Cancel" }).click();

    await expect(page).toHaveURL(/\/pricing\?checkout=cancelled/);
    await expect(page.getByText("Payment cancelled")).toBeVisible();
  });

  test("a cancelled checkout returns the user here and says they were not charged", async ({
    page,
  }) => {
    await mockProfile(page, FREE_PROFILE);

    await page.goto("/pricing?checkout=cancelled");

    await expect(page.getByText("Payment cancelled")).toBeVisible();
    await expect(page.getByText(/have not been charged/)).toBeVisible();
    // Still purchasable — the cancellation is informational, not terminal.
    await expect(
      page.getByRole("button", { name: /Upgrade to Dalil Pro/ }),
    ).toBeVisible();
  });

  test("a paid subscriber is not sold what they already own", async ({ page }) => {
    await mockProfile(page, PAID_PROFILE);

    await page.goto("/pricing");

    await expect(page.getByText("You're on Dalil Pro")).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Manage subscription/ }),
    ).toHaveAttribute("href", "/billing/manage");
    await expect(
      page.getByRole("button", { name: /Upgrade to Dalil Pro/ }),
    ).toHaveCount(0);
  });
});

test.describe("/billing/success", () => {
  test("does not declare success on the strength of the redirect alone", async ({
    page,
  }) => {
    // The tier has not flipped: the webhook has not landed (or never will,
    // because this URL was simply typed).
    await mockProfile(page, FREE_PROFILE);

    await page.goto("/billing/success?session_id=cs_test_typed_by_hand");

    await expect(page.getByText(/Activating your subscription/)).toBeVisible();
    await expect(page.getByText(/Your subscription is active/)).toHaveCount(0);
  });

  test("confirms and unlocks once the profile reports the paid tier", async ({
    page,
  }) => {
    // free, free, then paid — the shape of a webhook arriving a moment after
    // the browser does.
    let calls = 0;
    await page.route(`${GATEWAY}/api/profile`, (route) => {
      calls += 1;
      return route.fulfill(withCors(calls >= 3 ? PAID_PROFILE : FREE_PROFILE));
    });

    await page.goto("/billing/success?session_id=cs_test_e2e");

    await expect(page.getByText(/Your subscription is active/)).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("link", { name: /Take an IELTS exam/ }),
    ).toBeVisible();
  });
});

test.describe("Paid feature access after upgrade", () => {
  test("the exam page stops gating once the account is paid", async ({ page }) => {
    await mockProfile(page, PAID_PROFILE);
    await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
      route.fulfill(withCors({ attempts: [] })),
    );
    let sessionRequested = false;
    await page.route(`${GATEWAY}/api/exam/sessions`, (route) => {
      sessionRequested = true;
      return route.fulfill(
        withCors({ session_id: "sess-1", exam_type: "Academic" }),
      );
    });

    await page.goto("/exam");

    // Same race as above: wait until identity has resolved before clicking.
    // The sidebar's plan callout is the visible proof that it has, and for a
    // subscriber it now reads Dalil Pro rather than a hardcoded Free plan.
    await expect(
      page.getByRole("complementary").first().getByText("Dalil Pro"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Take Exam" }).first().click();

    // The gate short-circuit in exam/page.tsx only fires for a non-paid tier,
    // so a subscriber reaches the session request rather than the dialog.
    await expect.poll(() => sessionRequested).toBe(true);
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("the sidebar shows the real plan rather than a hardcoded Free badge", async ({
    page,
  }) => {
    await mockProfile(page, PAID_PROFILE);

    await page.goto("/dashboard");

    const sidebar = page.getByRole("complementary").first();
    await expect(sidebar.getByText("Dalil Pro")).toBeVisible();
    await expect(sidebar.getByText("Free plan")).toHaveCount(0);
  });
});

test.describe("/billing/manage", () => {
  test("a subscriber can cancel, and the page reflects the server's answer", async ({
    page,
  }) => {
    // Paid before the cancel call, free after it -- the page must re-read the
    // profile rather than assume the outcome it asked for.
    let cancelled = false;
    await page.route(`${GATEWAY}/api/profile`, (route) =>
      route.fulfill(withCors(cancelled ? FREE_PROFILE : PAID_PROFILE)),
    );
    await page.route(`${GATEWAY}/api/billing/cancel`, (route) => {
      cancelled = true;
      return route.fulfill(withCors({ subscriptionTier: "free" }));
    });

    await page.goto("/billing/manage");
    await page.getByRole("button", { name: "Cancel subscription" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel subscription" }).click();

    await expect(page.getByText(/subscription has been cancelled/)).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Upgrade to Dalil Pro/ }),
    ).toBeVisible();
  });

  test("a free user is offered the upgrade, not a cancellation", async ({
    page,
  }) => {
    await mockProfile(page, FREE_PROFILE);

    await page.goto("/billing/manage");

    await expect(
      page.getByRole("link", { name: /Upgrade to Dalil Pro/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Cancel subscription" }),
    ).toHaveCount(0);
  });
});

/*
 * The full payment lifecycle against the REAL stack -- Gateway, User service,
 * Postgres and Redis, with no route mocking at all -- lives in
 * tests/e2e/test_goa_039_subscription_lifecycle.py. That is where the two
 * definition-of-done card scenarios actually run. The specs here cover the
 * browser's half: what the user sees, and what the client sends.
 */

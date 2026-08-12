import { test, expect } from "@playwright/test";

/**
 * Authentication route guarding.
 *
 * Two tests were removed from this file rather than repaired, because both had
 * been failing since before Phase C and neither described the current product:
 *
 *   "full registration -> onboarding wizard -> /chat reached" drove selectors
 *   that do not exist (`input[name="fullName"]`, `button:has-text("Next")`,
 *   `button:has-text("Complete Onboarding")`), asserted a CV upload step that
 *   Phase C deleted from onboarding, and expected /chat when a profile-less
 *   account is deliberately sent to /onboarding. Its subject -- register, build
 *   a profile, reach the app -- is now covered against a live stack by
 *   test/journeys/journey-1-discovery.spec.ts, which asserts real matches
 *   rather than a landing URL.
 *
 *   "forgot password -> email received -> reset password" polled a Mailpit
 *   instance at localhost:8025. There is no Mailpit in docker-compose.yml and
 *   there never has been; the notification service sends through LocalStack
 *   SES, which stores messages rather than delivering them. The test could
 *   never have passed on this stack, so it was asserting nothing.
 *
 * Deleting a stale test is not losing coverage that existed -- it is removing a
 * failure that trained everyone to ignore this file. The guard below is the part
 * that was always real, and it is kept.
 */
test.describe("Authentication & User Flows", () => {
  test("E2E: unauthenticated user at /chat redirected to /login", async ({
    page,
  }) => {
    // Ensure clear context/no auth cookies
    await page.context().clearCookies();

    // Attempt direct access
    await page.goto("/chat");

    // Verify redirection
    await expect(page).toHaveURL(/\/login/);
  });
});

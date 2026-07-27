import { test, expect } from "@playwright/test";

// These prove the history pages render their error states gracefully instead
// of crashing. They deliberately do NOT exercise real data — the happy paths
// live in speaking-history-mocked.spec.ts.
//
// The unknown-session and unknown-token cases below are inherently negative
// (the backend answers 404 for them whether or not it's running), so they
// need no setup. The unreachable-backend case simulates the failure by
// aborting the request instead of relying on the Speaking Service happening
// to be down — depending on real infra state made it pass only by accident
// when nothing was running, and fail as soon as the service was up.

test.describe("GOA Speaking History", () => {
  test("history page shows an error state instead of crashing when the backend is unreachable", async ({
    page,
  }) => {
    await page.route(
      (url) => url.pathname === "/sessions",
      (route) => route.abort("failed"),
    );

    await page.goto("/speaking/history");

    await expect(page.getByText("Session History")).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  test("session detail page shows an error state for an unknown session", async ({
    page,
  }) => {
    await page.goto("/speaking/history/does-not-exist");

    await expect(
      page.getByRole("link", { name: /back to session history/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  test("public share page shows an error state for an unknown token, with no sidebar chrome", async ({
    page,
  }) => {
    await page.goto("/speaking/share/unknown-token");

    await expect(page.getByText("Shared Speaking Result")).toBeVisible();
    // Public page must not render the authenticated app's nav.
    await expect(page.getByRole("link", { name: "IELTS" })).toHaveCount(0);
  });
});

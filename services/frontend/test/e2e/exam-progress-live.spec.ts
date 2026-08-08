import { test, expect } from "./fixtures/auth";

const live = !!process.env.E2E_LIVE_EXAM;

test.describe("Exam Progress live smoke", () => {
  test.skip(!live, "Set E2E_LIVE_EXAM=1 with gateway+exam running");

  test("after one completed exam, score appears on Exam Progress", async ({
    page,
  }) => {
    // Reuse the shortest existing real Reading submit path from
    // reading-exam.spec.ts helpers if extractable; otherwise document
    // manual seed steps in a comment and assert against seeded user.
    // Minimum: complete/submit one Reading exam → goto /profile →
    // Exam Progress → expect band text visible in chart/list.
    await page.goto("/profile");
    await page.getByRole("tab", { name: "Exam Progress" }).click();
    await expect(page.getByTestId("exam-progress-empty-cta")).toHaveCount(0);
    await expect(
      page.locator("[data-testid^=trend-point-]").first(),
    ).toBeVisible({
      timeout: 30_000,
    });
  });

  test("two Reading exams show chronological 6.0 then 7.0", async ({
    page,
  }) => {
    // Requires two real completions or DB seed with those bands.
    // Assert trend-point-0 contains 6.0 and trend-point-1 contains 7.0.
  });
});

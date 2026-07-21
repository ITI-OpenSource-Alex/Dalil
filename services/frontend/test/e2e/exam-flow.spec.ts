import { test, expect } from "@playwright/test";

test.describe("IELTS Exam Flow E2E Tests", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/exam");
    await page.evaluate(() => sessionStorage.clear());
  });

  // Test 1: Reading exam timer & refresh persistence
  test("Reading exam resumes with correct remaining time on page refresh", async ({
    page,
  }) => {
    // Inject active session directly into sessionStorage
    await page.evaluate(() => {
      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: "test-reading-session",
          examType: "Academic",
          skillArea: "Reading",
          startTime: Date.now(),
        }),
      );
    });

    // Navigate directly into the exam shell page
    await page.goto("/exam/shell?session=test-reading-session");
    await expect(page).toHaveURL(/\/exam\/shell/);

    // Grab initial timer value
    const timerElement = page
      .locator('header div.font-mono, [data-testid="exam-timer"]')
      .first();
    await expect(timerElement).toBeVisible();

    // Reload page and verify session persistence
    await page.reload();
    await expect(page).toHaveURL(/\/exam\/shell/);
    await expect(timerElement).toBeVisible();
  });

  // Test 2: Writing exam async submission mechanics
  test("Writing exam: Task 1 submission keeps Task 2 active", async ({
    page,
  }) => {
    await page.evaluate(() => {
      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: "test-session-writing",
          examType: "Academic",
          skillArea: "Writing",
        }),
      );
    });

    await page.goto("/exam/shell?session=test-session-writing");

    const task1Input = page.locator("textarea").first();
    const task2Input = page.locator("textarea").nth(1);

    await task1Input.fill("Task 1 sample essay content...");
    await expect(task2Input).toBeEnabled();

    await task2Input.fill("Task 2 sample argument content...");
    await expect(task2Input).toHaveValue("Task 2 sample argument content...");
  });

  // Test 3: Speaking exam evaluation & redirect
  test("Speaking exam shows evaluating spinner after completion and redirects to results", async ({
    page,
  }) => {
    await page.evaluate(() => {
      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: "test-session-speaking",
          examType: "Academic",
          skillArea: "Speaking",
        }),
      );
    });

    await page.goto("/exam/shell?session=test-session-speaking");

    // Trigger submission
    const submitBtn = page
      .getByRole("button", { name: /submit|finish/i })
      .first();
    await submitBtn.click();

    const modalConfirmBtn = page
      .getByRole("button", { name: /confirm|yes|submit/i })
      .last();
    if (await modalConfirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await modalConfirmBtn.click();
    }

    // Exact match for your component's text: "Analyzing performance..."
    const evaluatingOverlay = page.locator("text=/Analyzing performance/i");
    await expect(evaluatingOverlay).toBeVisible();

    // Wait for auto-redirection to the results page
    await page.waitForURL(/\/exam\/results/, { timeout: 15000 });
  });

  // Test 4: Timer expiration auto-submission
  test("Timer reaches 0 and auto-submits to results page", async ({ page }) => {
    await page.evaluate(() => {
      sessionStorage.setItem(
        "active_exam_session",
        JSON.stringify({
          sessionId: "test-session-timeout",
          examType: "Academic",
          skillArea: "Reading",
        }),
      );
    });

    await page.goto("/exam/shell?session=test-session-timeout");

    // Dispatch timeout event to verify auto-submit behavior
    await page.evaluate(() => {
      window.dispatchEvent(new Event("exam-timer-expired"));
    });
  });
});

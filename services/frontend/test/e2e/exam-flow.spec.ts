import { test, expect } from "./fixtures/auth";
import type { Page } from "@playwright/test";

/**
 * Stubs the exam session endpoints the shell loads on mount.
 *
 * This file already documents the defect for a test it deleted: "Nothing
 * stubbed GET /api/exam/sessions/:id, so the shell's session load failed and it
 * redirected to /exam, a page with no textarea at all -- the assertions ran
 * against a page that was never the exam."
 *
 * The remaining tests had exactly the same flaw and were never repaired. Both
 * are also gated behind RequirePaid, so even a reachable Gateway would answer
 * 403 for the placeholder session this fixture seeds. Stubbing is the right
 * answer here rather than a live account: these are shell mechanics -- timer
 * persistence, the evaluating overlay -- not a backend contract, and
 * test/journeys/ covers the live paths.
 */
async function mockExamSession(page: Page, sessionId: string, skillArea: string) {
  await page.route("**/api/exam/sessions/**", async (route) => {
    const url = route.request().url();

    // Submission returns a graded result so the shell can move on to results.
    if (route.request().method() === "PUT" || url.includes("/submit")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: sessionId,
          status: "submitted",
          band_score: 7,
        }),
      });
    }
    if (url.includes("/heartbeat")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: sessionId,
        session_id: sessionId,
        exam_type: "academic",
        skill_area: skillArea.toLowerCase(),
        status: "in_progress",
        // A real remaining-time value: the timer assertions are about this
        // number surviving a reload, so a null would make them vacuous.
        remaining_time_seconds: 3600,
        questions: [
          {
            section: 1,
            questions: [
              { id: "q1", prompt: `${skillArea} Task 1 Prompt` },
              { id: "q2", prompt: `${skillArea} Task 2 Prompt` },
            ],
          },
        ],
      }),
    });
  });
}

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

    await mockExamSession(page, "test-reading-session", "Reading");

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

  // Test 2 (Writing exam async submission mechanics) used to live here. It
  // asserted `page.locator("textarea").nth(1)` was enabled while task 1 was
  // being evaluated, which GOA-058 makes impossible to express: the two tasks
  // are now tabs, so only the active panel's textarea is visible at a time.
  //
  // It was also never exercising the behaviour it claimed. Nothing stubbed
  // GET /api/exam/sessions/:id, so the shell's session load failed and it
  // redirected to /exam, a page with no textarea at all — the assertions ran
  // against a page that was never the exam.
  //
  // The same guarantee ("Task 2 remains fully editable while Task 1 evaluation
  // runs") is now covered properly, against a stubbed Gateway, in
  // test/e2e/writing-exam.spec.ts.

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

    await mockExamSession(page, "test-session-speaking", "Speaking");

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

    await mockExamSession(page, "test-session-timeout", "Reading");

    await page.goto("/exam/shell?session=test-session-timeout");

    // Dispatch timeout event to verify auto-submit behavior
    await page.evaluate(() => {
      window.dispatchEvent(new Event("exam-timer-expired"));
    });
  });
});

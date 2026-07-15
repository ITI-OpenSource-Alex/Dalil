import { test, expect } from "@playwright/test";

test.describe("GOA Writing Practice", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
  });

  test("opens writing mode", async ({ page }) => {
    await page.getByTitle("Writing Practice").click();

    await expect(page.getByTestId("essay-input")).toBeVisible();
  });

  test("submits essay for evaluation", async ({ page }) => {
    // Mock the chat endpoint
    await page.route("**/api/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
          'data: {"type":"writing_url","essayId":"1","sseUrl":"/api/writing/test"}',
          "",
          "",
        ].join("\n"),
      });
    });

    // Mock the writing evaluation stream
    await page.route("**/api/writing/test", async (route) => {
      console.log("Writing SSE endpoint hit");
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
          'data: {"type":"criterion","criterion":"grammar","band":7,"feedback":"Good grammar"}',
          "",
          'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}}}',
          "",
        ].join("\n"),
      });
    });

    await page.getByTitle("Writing Practice").click();

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    // Verify the evaluation panel updates
    await expect(page.getByText("Estimated Overall Band")).toBeVisible();

    await expect(page.getByText("7.0")).toBeVisible();

    await expect(page.getByText("Good grammar")).toBeVisible();

    await expect(page.getByText("Band 7.0")).toBeVisible();
  });
});

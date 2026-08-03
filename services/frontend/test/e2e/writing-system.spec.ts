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

    await page.route("**/api/writing/test", async (route) => {
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

    await expect(page.getByText("Estimated Overall Band")).toBeVisible();
    await expect(page.getByText("7.0")).toBeVisible();
    await expect(page.getByText("Good grammar")).toBeVisible();
    await expect(page.getByText("Band 7.0")).toBeVisible();
  });

  test("hover highlight → tooltip appears with correct content", async ({
    page,
  }) => {
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

    await page.route("**/api/writing/test", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
          'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}},"evaluations_full":[{"criterion":"grammar","text":"changed education","feedback":"Consider using a more precise grammatical structure."}]}',
          "",
        ].join("\n"),
      });
    });

    await page.getByTitle("Writing Practice").click();

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    const highlight = page.getByTestId("highlight-span");

    await expect(highlight).toBeVisible();

    await highlight.hover();

    await expect(
      page.getByText("Consider using a more precise grammatical structure."),
    ).toBeVisible();
  });

  test("submit essay → at least one highlight span visible with correct criterion colour", async ({
    page,
  }) => {
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

    await page.route("**/api/writing/test", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
          'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}},"evaluations_full":[{"criterion":"grammar","text":"changed education","feedback":"Grammar suggestion"}]}',
          "",
        ].join("\n"),
      });
    });

    await page.getByTitle("Writing Practice").click();

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    const highlight = page.getByTestId("highlight-span").first();

    await expect(highlight).toBeVisible();

    await expect(highlight).toHaveAttribute("data-criterion", "grammar");
  });

  test("download pdf button is present", async ({ page }) => {
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

    await page.route("**/api/writing/test", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
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

    await expect(page.getByTestId("download-pdf-button")).toBeVisible();
  });
});
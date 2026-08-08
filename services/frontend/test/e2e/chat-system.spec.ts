import { test, expect } from "./fixtures/auth";

test.describe("Dalil Chat System", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
  });

  test("should open chat page and load UI", async ({ page }) => {
    await expect(page.getByText("Dalil Assistant")).toBeVisible();

    await expect(page.getByTestId("chat-input")).toBeVisible();

    await expect(page.getByText("Hi 👋 I can help you find")).toBeVisible();
  });

  test("should send a message and display conversation", async ({ page }) => {
    await page.route("**/api/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
        },
        body: [
          'data: {"type":"metadata","intent":"chat","confidence":1}',
          "",
          'data: {"type":"token","content":"Hello"}',
          "",
          'data: {"type":"token","content":" from Dalil"}',
          "",
        ].join("\n"),
      });
    });

    await page.goto("/chat");

    await page
      .getByTestId("chat-input")
      .fill("Find scholarships for computer science");

    await page.getByTestId("send-message-button").click();

    await expect(page.getByTestId("user-message")).toContainText(
      "Find scholarships for computer science",
    );

    await expect(page.getByTestId("assistant-message").last()).toContainText(
      "Hello from Dalil",
    );
  });

  test("should disable sending an empty message", async ({ page }) => {
    const sendButton = page.getByTestId("send-message-button");

    await expect(sendButton).toBeDisabled();

    await expect(page.getByTestId("chat-input")).toHaveValue("");
  });

  test("should display error when chat service fails", async ({ page }) => {
    await page.route("**/api/chat", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: "Server error",
        }),
      });
    });

    await page.getByTestId("chat-input").fill("test failure");

    await page.getByTestId("send-message-button").click();

    await expect(
      page.getByText("Sorry, I am having trouble connecting right now."),
    ).toBeVisible();
  });
});

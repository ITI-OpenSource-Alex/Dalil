import { test, expect } from "@playwright/test";

test.describe("GOA Speaking Practice", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
  });

  test("opens speaking practice panel", async ({ page }) => {
    await page.getByTitle("Speaking Practice").click();

    await expect(page.getByTestId("speaking-panel")).toBeVisible();
  });

  test("starts microphone session", async ({ page }) => {
    await page.context().grantPermissions(["microphone"]);

    await page.getByTitle("Speaking Practice").click();

    await page.getByTestId("start-speaking-button").click();

    await expect(page.getByTestId("live-transcript")).toBeVisible();
  });

  test("shows the start button when the panel opens", async ({ page }) => {
    await page.goto("/chat");

    await page.getByTitle("Speaking Practice").click();

    await expect(page.getByTestId("start-speaking-button")).toBeVisible();
  });
});

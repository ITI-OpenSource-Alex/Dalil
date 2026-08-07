import { test, expect } from "./fixtures/auth";

// Phase D (docs/IA-REDESIGN-PROPOSAL.md): Writing Practice moved out of Chat
// onto its own page, /practice/writing. It creates the essay directly via
// POST /api/writing/essays/upload and evaluates it via
// POST /api/writing/essays/:id/evaluate -- the real Gateway routes -- rather
// than going through /api/chat's LLM intent-classification pipeline the way
// the chat-embedded version did. These tests mock those two real routes
// instead of /api/chat + a placeholder sseUrl.
async function mockEssayCreateAndEvaluate(
  page: import("@playwright/test").Page,
  evaluateBody: string,
) {
  await page.route("**/api/writing/essays/upload", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, status: "ready" }),
    });
  });

  await page.route("**/api/writing/essays/1/evaluate", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: evaluateBody,
    });
  });
}

test.describe("GOA Writing Practice", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/practice/writing");
  });

  test("shows the essay composer on load", async ({ page }) => {
    await expect(page.getByTestId("essay-input")).toBeVisible();
  });

  test("submits essay for evaluation", async ({ page }) => {
    await mockEssayCreateAndEvaluate(
      page,
      [
        'data: {"type":"criterion","criterion":"grammar","band":7,"feedback":"Good grammar"}',
        "",
        'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}}}',
        "",
      ].join("\n"),
    );

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    await expect(page.getByText("Estimated Overall Band")).toBeVisible();
    await expect(page.getByText("7.0", { exact: true })).toBeVisible();
    await expect(page.getByText("Good grammar")).toBeVisible();
    await expect(page.getByText("Band 7.0")).toBeVisible();
  });

  test("hover highlight → tooltip appears with correct content", async ({
    page,
  }) => {
    // start/end are character offsets into the submitted essay text --
    // "changed education" begins at index 15 in the string below.
    await mockEssayCreateAndEvaluate(
      page,
      [
        'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}},"evaluations_full":[{"criterion":"grammar","band_score":7,"feedback":"Good grammar","highlighted_issues":[{"text":"changed education","issue":"Consider using a more precise grammatical structure.","suggestion":"Try \'transformed\' or \'reshaped\'.","start":15,"end":32}]}]}',
        "",
      ].join("\n"),
    );

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
    await mockEssayCreateAndEvaluate(
      page,
      [
        'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}},"evaluations_full":[{"criterion":"grammar","band_score":7,"feedback":"Good grammar","highlighted_issues":[{"text":"changed education","issue":"Grammar suggestion","suggestion":"Grammar suggestion","start":15,"end":32}]}]}',
        "",
      ].join("\n"),
    );

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    const highlight = page.getByTestId("highlight-span").first();

    await expect(highlight).toBeVisible();

    await expect(highlight).toHaveAttribute("data-criterion", "grammar");
  });

  test("download pdf button is present", async ({ page }) => {
    await mockEssayCreateAndEvaluate(
      page,
      [
        'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}}}',
        "",
      ].join("\n"),
    );

    await page
      .getByTestId("essay-input")
      .fill("Technology has changed education significantly.");

    await page.getByTestId("submit-essay-button").click();

    await expect(page.getByTestId("download-pdf-button")).toBeVisible();
  });
});

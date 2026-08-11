import { test, expect } from "./fixtures/auth";

test.describe("Dalil Chat System", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/profile", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-user",
          email: "student@example.com",
          subscriptionTier: "free",
          isVerified: true,
          profile: null,
        }),
      });
    });
    await page.route("**/api/chat/sessions/*/history", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });
    await page.goto("/dashboard");
  });

  test("opens the floating chat and loads the general chat UI", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Chat" })).toHaveCount(0);
    await page.getByTestId("dalil-chat-pill").click();
    await expect(
      page.getByRole("heading", { name: "Dalil Assistant", exact: true }),
    ).toBeVisible();

    await expect(page.getByTestId("chat-input")).toBeVisible();
    await expect(page.getByTestId("chat-input")).toBeFocused();

    await expect(page.getByText("Hi 👋 I can help you find")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("dalil-chat-panel")).toBeHidden();
    await expect(page.getByTestId("dalil-chat-pill")).toBeFocused();
  });

  test("uses an accessible mobile bottom sheet", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    await page.getByTestId("dalil-chat-pill").click();

    const panel = page.getByTestId("dalil-chat-panel");
    await expect(panel).toBeVisible();
    await panel.evaluate((element) =>
      Promise.all(element.getAnimations().map((animation) => animation.finished)),
    );
    const bounds = await panel.boundingBox();
    expect(bounds).not.toBeNull();
    // The sheet spans the mobile viewport edge-to-edge after its opening
    // animation settles.
    expect(bounds!.x).toBeLessThan(1);
    expect(bounds!.width).toBeGreaterThan(374);
    expect(Math.round(bounds!.y + bounds!.height)).toBe(667);
    await expect(page.getByTestId("chat-input")).toBeFocused();
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

    await page.getByTestId("dalil-chat-pill").click();

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
    await page.getByTestId("dalil-chat-pill").click();
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

    await page.getByTestId("dalil-chat-pill").click();
    await page.getByTestId("chat-input").fill("test failure");

    await page.getByTestId("send-message-button").click();

    await expect(
      page.getByText(
        "I'm having trouble connecting right now. Please check your connection and try again.",
      ),
    ).toBeVisible();
  });

  test("keeps a draft and conversation when the panel is closed and reopened", async ({ page }) => {
    await page.getByTestId("dalil-chat-pill").click();
    await page.getByTestId("chat-input").fill("My own unfinished question");
    await page.getByRole("button", { name: "Close Dalil chat" }).click();

    await page.getByTestId("dalil-chat-pill").click();
    await expect(page.getByTestId("chat-input")).toHaveValue(
      "My own unfinished question",
    );
  });

  test("Ask Dalil pastes editable programme context without auto-sending", async ({ page }) => {
    await page.route("**/api/profile", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-user",
          email: "student@example.com",
          subscriptionTier: "free",
          isVerified: true,
          profile: {
            userId: "e2e-user",
            degreeLevel: "bachelor",
            gpa: 3.4,
            ieltsScore: 7,
            ieltsListening: null,
            ieltsReading: null,
            ieltsWriting: null,
            ieltsSpeaking: null,
            targetCountries: ["Germany"],
            fieldOfStudy: "Computer Science",
            ects: 180,
            workExperienceYears: 1,
            extracurricularsScore: 0,
            gpaScale: "4.0",
          },
        }),
      });
    });
    await page.route("**/api/opportunities/query", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          programs: [
            {
              programId: "tum-cs",
              programName: "MSc Computer Science",
              university: "Technical University of Munich",
              country: "Germany",
              deadline: null,
              result: { score: 91, blocked_by: null },
            },
          ],
        }),
      });
    });

    await page.goto("/opportunities");
    await page.getByRole("button", { name: "Ask Dalil" }).click();

    const input = page.getByTestId("chat-input");
    await expect(page.getByTestId("dalil-chat-panel")).toBeVisible();
    await expect(input).toBeFocused();
    await expect(input).toHaveValue(/MSc Computer Science/);
    await expect(input).toHaveValue(/Technical University of Munich/);
    await input.fill("What scholarships could I use for this programme?");
    await expect(input).toHaveValue(
      "What scholarships could I use for this programme?",
    );
    await expect(page.getByTestId("user-message")).toHaveCount(0);
  });
});

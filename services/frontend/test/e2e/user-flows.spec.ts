import { test, expect } from "@playwright/test";

test.describe("Authentication & User Flows", () => {
  test("E2E: full registration → onboarding wizard → CV upload → /chat reached", async ({
    page,
  }) => {
    // 1. Full Registration
    await page.goto("/register");
    await page.fill(
      'input[name="email"]',
      `testuser_${Date.now()}@example.com`,
    );
    await page.fill('input[name="password"]', "SecurePassword123!");
    await page.click('button[type="submit"]');

    // 2. Onboarding Wizard
    await expect(page).toHaveURL(/\/onboarding/);
    await page.fill('input[name="fullName"]', "Jane Doe");
    await page.click('button:has-text("Next")');

    // 3. CV Upload
    const fileChooserPromise = page.waitForEvent("filechooser");
    await page.click('button:has-text("Upload CV")');
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: "resume.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 sample content"),
    });

    await page.click('button:has-text("Complete Onboarding")');

    // 4. /chat reached
    await expect(page).toHaveURL(/\/chat/);
    await expect(page.locator("h1")).toContainText("Chat");
  });

  test("E2E: forgot password → email received → reset password → login with new password", async ({
    page,
    request,
  }) => {
    const testEmail = "user_reset@example.com";
    const newPassword = "NewSecurePassword123!";

    // 1. Forgot password request
    await page.goto("/forgot-password");
    await page.fill('input[name="email"]', testEmail);
    await page.click('button[type="submit"]');
    await expect(page.locator(".success-message")).toBeVisible();

    // 2. Email received (Mocking or fetching token from test email API/Mailpit)
    // Adjust endpoint to match your test mail server (e.g., Mailhog, Mailpit, or backend test endpoint)
    const mailResponse = await request.get(
      `http://localhost:8025/api/v1/messages`,
    );
    const messages = await mailResponse.json();
    const latestEmail = messages.find(
      (m: any) => m.To[0].Address === testEmail,
    );

    // Extract reset link/token from email body
    const resetUrlMatch = latestEmail.Text.match(
      /https?:\/\/[^\s"]+\/reset-password\?token=[^\s"']+/,
    );
    const resetUrl = resetUrlMatch[0];

    // 3. Reset password
    await page.goto(resetUrl);
    await page.fill('input[name="password"]', newPassword);
    await page.fill('input[name="confirmPassword"]', newPassword);
    await page.click('button[type="submit"]');

    // 4. Login with new password
    await page.goto("/login");
    await page.fill('input[name="email"]', testEmail);
    await page.fill('input[name="password"]', newPassword);
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/dashboard|\/chat/);
  });

  test("E2E: unauthenticated user at /chat redirected to /login", async ({
    page,
  }) => {
    // Ensure clear context/no auth cookies
    await page.context().clearCookies();

    // Attempt direct access
    await page.goto("/chat");

    // Verify redirection
    await expect(page).toHaveURL(/\/login/);
  });
});

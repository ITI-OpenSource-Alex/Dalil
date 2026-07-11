# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: test\e2e\user-flows.spec.ts >> Authentication & User Flows >> E2E: full registration → onboarding wizard → CV upload → /chat reached
- Location: test\e2e\user-flows.spec.ts:4:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.fill: Test timeout of 30000ms exceeded.
Call log:
  - waiting for locator('input[name="email"]')

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - heading "Register Page" [level=1] [ref=e2]
  - button "Open Next.js Dev Tools" [ref=e8] [cursor=pointer]:
    - img [ref=e9]
  - alert [ref=e12]
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | test.describe("Authentication & User Flows", () => {
  4  |   test("E2E: full registration → onboarding wizard → CV upload → /chat reached", async ({
  5  |     page,
  6  |   }) => {
  7  |     // 1. Full Registration
  8  |     await page.goto("/register");
> 9  |     await page.fill(
     |                ^ Error: page.fill: Test timeout of 30000ms exceeded.
  10 |       'input[name="email"]',
  11 |       `testuser_${Date.now()}@example.com`,
  12 |     );
  13 |     await page.fill('input[name="password"]', "SecurePassword123!");
  14 |     await page.click('button[type="submit"]');
  15 | 
  16 |     // 2. Onboarding Wizard
  17 |     await expect(page).toHaveURL(/\/onboarding/);
  18 |     await page.fill('input[name="fullName"]', "Jane Doe");
  19 |     await page.click('button:has-text("Next")');
  20 | 
  21 |     // 3. CV Upload
  22 |     const fileChooserPromise = page.waitForEvent("filechooser");
  23 |     await page.click('button:has-text("Upload CV")');
  24 |     const fileChooser = await fileChooserPromise;
  25 |     await fileChooser.setFiles({
  26 |       name: "resume.pdf",
  27 |       mimeType: "application/pdf",
  28 |       buffer: Buffer.from("%PDF-1.4 sample content"),
  29 |     });
  30 | 
  31 |     await page.click('button:has-text("Complete Onboarding")');
  32 | 
  33 |     // 4. /chat reached
  34 |     await expect(page).toHaveURL(/\/chat/);
  35 |     await expect(page.locator("h1")).toContainText("Chat");
  36 |   });
  37 | 
  38 |   test("E2E: forgot password → email received → reset password → login with new password", async ({
  39 |     page,
  40 |     request,
  41 |   }) => {
  42 |     const testEmail = "user_reset@example.com";
  43 |     const newPassword = "NewSecurePassword123!";
  44 | 
  45 |     // 1. Forgot password request
  46 |     await page.goto("/forgot-password");
  47 |     await page.fill('input[name="email"]', testEmail);
  48 |     await page.click('button[type="submit"]');
  49 |     await expect(page.locator(".success-message")).toBeVisible();
  50 | 
  51 |     // 2. Email received (Mocking or fetching token from test email API/Mailpit)
  52 |     // Adjust endpoint to match your test mail server (e.g., Mailhog, Mailpit, or backend test endpoint)
  53 |     const mailResponse = await request.get(
  54 |       `http://localhost:8025/api/v1/messages`,
  55 |     );
  56 |     const messages = await mailResponse.json();
  57 |     const latestEmail = messages.find(
  58 |       (m: any) => m.To[0].Address === testEmail,
  59 |     );
  60 | 
  61 |     // Extract reset link/token from email body
  62 |     const resetUrlMatch = latestEmail.Text.match(
  63 |       /https?:\/\/[^\s"]+\/reset-password\?token=[^\s"']+/,
  64 |     );
  65 |     const resetUrl = resetUrlMatch[0];
  66 | 
  67 |     // 3. Reset password
  68 |     await page.goto(resetUrl);
  69 |     await page.fill('input[name="password"]', newPassword);
  70 |     await page.fill('input[name="confirmPassword"]', newPassword);
  71 |     await page.click('button[type="submit"]');
  72 | 
  73 |     // 4. Login with new password
  74 |     await page.goto("/login");
  75 |     await page.fill('input[name="email"]', testEmail);
  76 |     await page.fill('input[name="password"]', newPassword);
  77 |     await page.click('button[type="submit"]');
  78 | 
  79 |     await expect(page).toHaveURL(/\/dashboard|\/chat/);
  80 |   });
  81 | 
  82 |   test("E2E: unauthenticated user at /chat redirected to /login", async ({
  83 |     page,
  84 |   }) => {
  85 |     // Ensure clear context/no auth cookies
  86 |     await page.context().clearCookies();
  87 | 
  88 |     // Attempt direct access
  89 |     await page.goto("/chat");
  90 | 
  91 |     // Verify redirection
  92 |     await expect(page).toHaveURL(/\/login/);
  93 |   });
  94 | });
  95 | 
```
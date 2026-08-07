import { test, expect } from "@playwright/test";

// GOA-035: application checklist, end to end through the real Gateway/RAG/User
// stack (per the ticket's Definition of Done). Registers a fresh user per run
// (same pattern as user-flows.spec.ts) since checklist generation is scoped by
// the authenticated user's real id (BUG-047 fix), not a shared fixture account.
test.describe("Application Checklist (GOA-035)", () => {
  const SEED_PROGRAM_ID = "11111111-1111-1111-1111-111111111111"; // TU Munich, Germany

  async function registerAndLogin(page: import("@playwright/test").Page) {
    const email = `checklist_e2e_${Date.now()}@example.com`;
    const password = "SecurePassword123!";

    // RegisterForm posts {email, password} only and does not log the caller in --
    // it redirects to /login on success (components/auth/RegisterForm.tsx).
    await page.goto("/register");
    await page.fill("#register-email", email);
    await page.fill("#register-password", password);
    await page.fill("#register-confirm-password", password);
    await page.click("#register-submit-btn");
    await expect(page).toHaveURL(/\/login/);

    await page.fill("#login-email", email);
    await page.fill("#login-password", password);
    await page.click("#login-submit-btn");
    await expect(page).toHaveURL(/\/chat/);
  }

  test("checklist loads, checkbox state persists after refresh", async ({ page }) => {
    await registerAndLogin(page);

    await page.goto(`/checklist/${SEED_PROGRAM_ID}`);

    // Generated on first load (GOA-084 get-or-create); at least one phase renders.
    const firstItem = page.getByTestId("checklist-item").first();
    await expect(firstItem).toBeVisible({ timeout: 15000 });

    const checkbox = firstItem.getByRole("checkbox");
    const wasChecked = (await checkbox.getAttribute("aria-checked")) === "true";
    await checkbox.click();
    await expect(checkbox).toHaveAttribute(
      "aria-checked",
      wasChecked ? "false" : "true",
    );

    // Definition of Done: state persists after refresh.
    await page.reload();
    const reloadedFirstItem = page.getByTestId("checklist-item").first();
    await expect(reloadedFirstItem.getByRole("checkbox")).toHaveAttribute(
      "aria-checked",
      wasChecked ? "false" : "true",
    );
  });

  test("Financial Requirements phase is omitted when the backend has no visa data for the program's country", async ({
    page,
  }) => {
    await registerAndLogin(page);
    await page.goto(`/checklist/${SEED_PROGRAM_ID}`);

    await expect(page.getByTestId("checklist-item").first()).toBeVisible({
      timeout: 15000,
    });

    // The seeded dev DB ships no visa_requirements rows (GOA-108/109 data
    // population is a separate ticket), so this must render nothing rather than
    // an empty "Financial Requirements" heading.
    const financialPhase = page.locator(
      '[data-testid="checklist-phase"][data-phase="Financial Requirements"]',
    );
    await expect(financialPhase).toHaveCount(0);
  });

  test("PDF export button is present and triggers the browser print dialog", async ({
    page,
  }) => {
    await registerAndLogin(page);
    await page.goto(`/checklist/${SEED_PROGRAM_ID}`);
    await expect(page.getByTestId("checklist-item").first()).toBeVisible({
      timeout: 15000,
    });

    let printCalled = false;
    await page.exposeFunction("__notifyPrintCalled", () => {
      printCalled = true;
    });
    await page.addInitScript(() => {
      window.print = () => {
        (window as unknown as { __notifyPrintCalled: () => void }).__notifyPrintCalled();
      };
    });
    await page.reload();
    await expect(page.getByTestId("checklist-item").first()).toBeVisible({
      timeout: 15000,
    });

    await page.getByRole("button", { name: "Export as PDF" }).click();
    await expect.poll(() => printCalled).toBe(true);
  });
});

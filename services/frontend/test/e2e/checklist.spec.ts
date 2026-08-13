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

    // Landing anywhere authenticated is the requirement; WHICH page is a
    // product decision this test should not pin.
    //
    // It asserted /chat and failed all three cases before reaching a checklist.
    // The app was right: LoginForm sends an account whose profile is still
    // empty to /onboarding, because dropping a new user into chat with nothing
    // to work from is a worse landing than the wizard. A fresh registration is
    // exactly that account, so /chat was never the destination.
    //
    // What the checklist route actually needs is the access_token cookie that
    // middleware.ts guards on -- not a particular landing page.
    await expect(page).toHaveURL(/\/(chat|onboarding)/);
    await expect
      .poll(async () =>
        (await page.context().cookies()).some((c) => c.name === "access_token"),
      )
      .toBe(true);
  }

  test("checklist loads, checkbox state persists after refresh", async ({ page }) => {
    await registerAndLogin(page);

    await page.goto(`/checklist/${SEED_PROGRAM_ID}`);

    // Generated on first load (GOA-084 get-or-create); at least one phase renders.
    const firstItem = page.getByTestId("checklist-item").first();
    await expect(firstItem).toBeVisible({ timeout: 15000 });

    // toBeChecked(), not toHaveAttribute("aria-checked").
    //
    // components/ui/checkbox was rebuilt on a real <input type="checkbox">
    // instead of the <button role="checkbox" aria-checked> it used to be, for
    // the keyboard handling, form participation and screen-reader announcement
    // a native control brings for free. A native checkbox carries its state as
    // the `checked` DOM PROPERTY and has no aria-checked attribute at all, so
    // the old assertion read null and failed against a control that works.
    const checkbox = firstItem.getByRole("checkbox");
    const wasChecked = await checkbox.isChecked();
    await checkbox.click();
    if (wasChecked) {
      await expect(checkbox).not.toBeChecked();
    } else {
      await expect(checkbox).toBeChecked();
    }

    // Definition of Done: state persists after refresh.
    await page.reload();
    const reloadedCheckbox = page
      .getByTestId("checklist-item")
      .first()
      .getByRole("checkbox");
    if (wasChecked) {
      await expect(reloadedCheckbox).not.toBeChecked();
    } else {
      await expect(reloadedCheckbox).toBeChecked();
    }
  });

  test("Financial Requirements phase tracks whether the backend actually has visa data", async ({
    page,
    request,
  }) => {
    await registerAndLogin(page);
    await page.goto(`/checklist/${SEED_PROGRAM_ID}`);

    await expect(page.getByTestId("checklist-item").first()).toBeVisible({
      timeout: 15000,
    });

    // This test used to assert the phase was ALWAYS absent, on the stated
    // premise that "the seeded dev DB ships no visa_requirements rows
    // (GOA-108/109 data population is a separate ticket)". That premise is no
    // longer true -- the visa ingestion handoff has run and Germany, which is
    // this seed programme's country, now has data. The phase correctly renders,
    // and the old assertion had turned into a test that failed whenever the
    // feature worked.
    //
    // The real requirement was never "always absent". It is that the UI must
    // not invent a phase it has no data for, and must not hide one it does --
    // the "never let unknown and zero collapse" rule. So the expectation is
    // derived from the backend rather than hardcoded.
    const financials = await request.get(
      `http://localhost:8080/api/checklists/${SEED_PROGRAM_ID}/financial`,
      {
        headers: {
          Cookie: (await page.context().cookies())
            .filter((c) => c.name === "access_token")
            .map((c) => `${c.name}=${c.value}`)
            .join("; "),
        },
      },
    );

    let hasVisaData = false;
    if (financials.ok()) {
      const body = await financials.json();
      const items = body?.items ?? body?.requirements ?? [];
      hasVisaData = Array.isArray(items) && items.length > 0;
    }

    const financialPhase = page.locator(
      '[data-testid="checklist-phase"][data-phase="Financial Requirements"]',
    );

    if (hasVisaData) {
      await expect(
        financialPhase,
        "the backend returned financial requirements for this programme's " +
          "country, but the checklist omitted the phase entirely",
      ).toHaveCount(1);
      await expect(page.getByTestId("financial-item").first()).toBeVisible();
    } else {
      await expect(
        financialPhase,
        "no visa data for this programme's country, so the checklist must " +
          "render nothing rather than an empty 'Financial Requirements' heading",
      ).toHaveCount(0);
    }
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

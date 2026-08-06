import { test, chromium } from "@playwright/test";
import { playAudit } from "playwright-lighthouse";

test.describe("SEO & Accessibility Audits", () => {
  test("SEO: lighthouse accessibility score > 90 on landing page", async () => {
    // Lighthouse requires remote debugging port
    const browser = await chromium.launch({
      args: ["--remote-debugging-port=9222"],
    });

    const page = await browser.newPage();
    await page.goto("http://localhost:3000/"); // Adjust port to match your local app target

    await playAudit({
      page,
      thresholds: {
        accessibility: 90,
      },
      port: 9222,
      reports: {
        formats: {
          html: true, // Generates visual report in root
        },
        directory: "lighthouse-reports",
      },
    });

    await browser.close();
  });
});

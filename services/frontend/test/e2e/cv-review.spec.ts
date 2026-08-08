import { test, expect, Page } from "./fixtures/auth";

// CV Review (Phase E, docs/IA-REDESIGN-PROPOSAL.md) is reached through the
// Gateway (localhost:8080), a different origin than the frontend
// (localhost:3000) -- same reasoning as speaking-history-mocked.spec.ts:
// every call here uses credentials: "include", so a mocked response needs an
// explicit CORS origin, not a wildcard, or the browser rejects it.
const CV_API_BASE = "http://localhost:8080/api/writing/cv";

function withCors(body: unknown, status = 200) {
  return {
    status,
    contentType: "application/json",
    headers: {
      "Access-Control-Allow-Origin": "http://localhost:3000",
      "Access-Control-Allow-Credentials": "true",
    },
    body: JSON.stringify(body),
  };
}

async function mockNoCvUploaded(page: Page) {
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
}

const READY_CV = {
  cvId: 1,
  s3Key: "cvs/user-1/resume.pdf",
  originalFilename: "resume.pdf",
  status: "ready",
  uploadedAt: "2026-01-01T00:00:00Z",
};

test.describe("Dalil CV Review", () => {
  test("shows the upload dropzone when no CV has been uploaded yet", async ({ page }) => {
    await mockNoCvUploaded(page);

    await page.goto("/cv-review");

    await expect(
      page.getByLabel(/Upload your CV as a PDF, DOC or DOCX/),
    ).toBeVisible();
  });

  test("uploading a CV shows it as processing", async ({ page }) => {
    await mockNoCvUploaded(page);
    await page.route(`${CV_API_BASE}/upload`, (route) =>
      route.fulfill(
        withCors({ cvId: 1, status: "processing", s3Key: "cvs/user-1/resume.pdf" }, 200),
      ),
    );

    await page.goto("/cv-review");
    await page
      .locator('input[type="file"]')
      .setInputFiles({
        name: "resume.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("%PDF-1.7\nresume\n%%EOF"),
      });

    await expect(page.getByText("resume.pdf")).toBeVisible();
    await expect(page.getByText(/Processing/)).toBeVisible();
  });

  test("a ready CV can be reviewed and renders section-by-section results", async ({ page }) => {
    await page.route(`${CV_API_BASE}/latest`, (route) => route.fulfill(withCors(READY_CV)));
    await page.route(`${CV_API_BASE}/review`, (route) =>
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'event: section\ndata: {"name":"Skills","score":85,"issues":["Missing quantified impact"],"suggestions":["Add measurable outcomes"]}',
          "",
          'event: complete\ndata: {"overallScore":82,"sections":[{"name":"Skills","score":85,"issues":["Missing quantified impact"],"suggestions":["Add measurable outcomes"]}]}',
          "",
        ].join("\n"),
      }),
    );

    await page.goto("/cv-review");
    await expect(page.getByText("Ready for review")).toBeVisible();

    await page.getByLabel("Target country").fill("Germany");
    await page.getByLabel("Target field of study").fill("Computer Science");
    await page.getByRole("button", { name: "Start CV Review" }).click();

    await expect(page.getByText("Overall score 82/100")).toBeVisible();
    await expect(page.getByText("Missing quantified impact")).toBeVisible();
    await expect(page.getByText("Add measurable outcomes")).toBeVisible();
  });

  test("a free account starting a review sees the upgrade dialog, not a raw error", async ({ page }) => {
    await page.route(`${CV_API_BASE}/latest`, (route) => route.fulfill(withCors(READY_CV)));
    await page.route(`${CV_API_BASE}/review`, (route) =>
      route.fulfill(
        withCors({ error: "subscription_required", upgradeUrl: "/#pricing" }, 403),
      ),
    );

    await page.goto("/cv-review");
    await page.getByLabel("Target country").fill("Germany");
    await page.getByLabel("Target field of study").fill("Computer Science");
    await page.getByRole("button", { name: "Start CV Review" }).click();

    await expect(
      page.getByRole("heading", { name: "CV review is part of Dalil Pro" }),
    ).toBeVisible();
  });

  test("review history is an honest empty state, not fabricated entries", async ({ page }) => {
    await mockNoCvUploaded(page);

    await page.goto("/cv-review");

    await expect(page.getByText("Review history isn't available yet")).toBeVisible();
  });
});

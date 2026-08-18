import { test, expect, Page } from "./fixtures/auth";

const GATEWAY = "http://localhost:8080";
const CV_API_BASE = `${GATEWAY}/api/writing/cv`;
const PROGRAM_ID = "program-1";

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

const READY_CV = {
  cvId: 1,
  s3Key: "cvs/user-1/resume.pdf",
  originalFilename: "resume.pdf",
  status: "ready",
  uploadedAt: "2026-01-01T00:00:00Z",
};

async function mockProfile(page: Page) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(
      withCors({
        id: "user-1",
        email: "student@example.com",
        subscriptionTier: "paid",
        isVerified: true,
        profile: {},
      }),
    ),
  );
}

async function mockChecklist(page: Page) {
  await page.route(`${GATEWAY}/api/checklists/${PROGRAM_ID}`, (route) =>
    route.fulfill(
      withCors({
        checklistId: "checklist-1",
        programId: PROGRAM_ID,
        programName: "MSc Computer Science",
        country: "Germany",
        discipline: "computer_science",
        generatedBy: "requirements",
        items: [
          {
            itemId: "ielts_certificate",
            title: "IELTS certificate",
            description: "Provide a valid result showing the required level.",
            category: "language",
            checked: false,
          },
          {
            itemId: "transcript",
            title: "Prepare transcript",
            description: "Obtain an official transcript.",
            category: "documents",
            checked: false,
          },
          ...Array.from({ length: 5 }, (_, index) => ({
            itemId: `document-${index}`,
            title: `Supporting document ${index + 1}`,
            description: "Prepare the verified document requested by admissions.",
            category: "documents",
            checked: false,
          })),
        ],
      }),
    ),
  );
  await page.route(`${GATEWAY}/api/checklists/${PROGRAM_ID}/financial`, (route) =>
    route.fulfill(
      withCors({
        programId: PROGRAM_ID,
        items: [
          {
            type: "informational",
            country: "Germany",
            issuingBody: "Federal Foreign Office",
            message: "Provide current proof of funds for the study period.",
            sourceUrl: "https://example.com/official-funds",
            lastVerifiedAt: "2026-08-01T00:00:00Z",
          },
          {
            type: "informational",
            country: "Germany",
            issuingBody: "University admissions office",
            message: "Confirm whether a blocked account is required.",
            sourceUrl: "https://example.com/admissions-funds",
            lastVerifiedAt: "2026-08-01T00:00:00Z",
          },
        ],
      }),
    ),
  );
}

test.describe("Programme CV recommendations", () => {
  test.beforeEach(async ({ page }) => {
    await mockProfile(page);
  });

  test("the legacy CV page redirects to the profile CV tab", async ({ page }) => {
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
    );

    await page.goto("/cv-review");

    await expect(page).toHaveURL(/\/profile\?tab=cv$/);
    await expect(page.getByRole("tab", { name: "CV" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("a checklist without a CV points to the profile instead of embedding an upload", async ({
    page,
  }) => {
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
    );

    await page.goto(`/checklist/${PROGRAM_ID}`);

    await expect(page.getByText("CV recommendations")).toBeVisible();
    await expect(page.getByRole("link", { name: "Add CV to profile" })).toHaveAttribute(
      "href",
      "/profile?tab=cv",
    );
    await expect(page.locator('input[type="file"]')).toHaveCount(0);
  });

  test("uneven phase cards flow independently without a blank grid row", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
    );

    await page.goto(`/checklist/${PROGRAM_ID}`);

    const language = await page
      .locator('[data-testid="checklist-phase"][data-phase="Language Prep"]')
      .boundingBox();
    const documents = await page
      .locator('[data-testid="checklist-phase"][data-phase="Documents"]')
      .boundingBox();
    const financial = await page
      .locator(
        '[data-testid="checklist-phase"][data-phase="Financial Requirements"]',
      )
      .boundingBox();

    expect(language).not.toBeNull();
    expect(documents).not.toBeNull();
    expect(financial).not.toBeNull();
    expect(Math.abs(financial!.x - language!.x)).toBeLessThan(4);
    expect(documents!.x).toBeGreaterThan(language!.x);
    expect(financial!.y - (language!.y + language!.height)).toBeLessThan(40);
  });

  test("a CV lookup outage shows recovery actions instead of an endless spinner", async ({
    page,
  }) => {
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors({ detail: "Writing service unavailable" }, 502)),
    );

    await page.goto(`/checklist/${PROGRAM_ID}`);

    await expect(page.getByText("We couldn't check your profile CV")).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Manage CV" })).toHaveAttribute(
      "href",
      "/profile?tab=cv",
    );
    await expect(page.getByText("Checking your profile CV…")).toHaveCount(0);
  });

  test("review uses the checklist programme and renders recommendations in place", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors(READY_CV)),
    );

    let reviewPayload: Record<string, unknown> | null = null;
    await page.route(`${CV_API_BASE}/review`, async (route) => {
      reviewPayload = route.request().postDataJSON();
      const sections = [
        {
          name: "Skills gaps",
          score: 74,
          issues: ["Missing research evidence"],
          suggestions: ["Add the database project that matches this programme"],
        },
        { name: "Structure and formatting", score: 74, issues: [], suggestions: [] },
        { name: "ATS keyword optimization", score: 74, issues: [], suggestions: [] },
        { name: "Length appropriateness", score: 74, issues: [], suggestions: [] },
        {
          name: "Country-specific conventions",
          score: 74,
          issues: [],
          suggestions: [],
        },
      ];
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'event: section\ndata: {"name":"Skills gaps","score":74,"issues":["Missing research evidence"],"suggestions":["Add the database project that matches this programme"]}',
          "",
          `event: complete\ndata: ${JSON.stringify({ overallScore: 74, sections })}`,
          "",
        ].join("\n"),
      });
    });

    await page.goto(`/checklist/${PROGRAM_ID}`);

    await expect(page.getByText("Tailored to MSc Computer Science in Germany.")).toBeVisible();
    await expect(page.getByLabel("Target country")).toHaveCount(0);
    await page.getByRole("button", { name: "Review for this programme" }).click();

    await expect(page.getByText("Programme fit 74/100")).toBeVisible();
    await expect(page.getByText("Missing research evidence")).toBeVisible();
    await expect(
      page.getByText("Add the database project that matches this programme"),
    ).toBeVisible();
    const reviewCard = await page
      .getByTestId("program-cv-recommendations")
      .boundingBox();
    expect(reviewCard?.width).toBeGreaterThan(900);

    const issuesColumn = await page.getByText("What to fix").first().boundingBox();
    const recommendationsColumn = await page
      .getByText("Recommended changes")
      .first()
      .boundingBox();
    expect(issuesColumn).not.toBeNull();
    expect(recommendationsColumn).not.toBeNull();
    expect(recommendationsColumn!.x).toBeGreaterThan(issuesColumn!.x);
    expect(Math.abs(recommendationsColumn!.y - issuesColumn!.y)).toBeLessThan(4);
    expect(reviewPayload).toEqual({
      cvS3Key: READY_CV.s3Key,
      programId: PROGRAM_ID,
    });
  });

  test("a slow review keeps a visible label, progress, and cancel control", async ({
    page,
  }) => {
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors(READY_CV)),
    );
    await page.route(`${CV_API_BASE}/review`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'event: complete\ndata: {"overallScore":80,"sections":[{"name":"Skills gaps","score":80,"issues":[],"suggestions":[]}]}',
          "",
        ].join("\n"),
      });
    });

    await page.goto(`/checklist/${PROGRAM_ID}`);
    await page.getByRole("button", { name: "Review for this programme" }).click();

    await expect(page.getByRole("button", { name: "Reviewing 0 of 5" })).toBeVisible();
    await expect(page.getByText("0 of 5 checks complete")).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(
      page.getByText("Review stopped. Any recommendations already received are kept below."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Review for this programme" }),
    ).toBeEnabled();
  });

  test("a review continues while navigating away and is restored on return", async ({
    page,
  }) => {
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors(READY_CV)),
    );
    await page.route(`${CV_API_BASE}/review`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 800));
      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'event: complete\ndata: {"overallScore":83,"sections":[{"name":"Structure and formatting","score":83,"issues":[],"suggestions":["Lead with your strongest relevant project"]}]}',
          "",
        ].join("\n"),
      });
    });

    await page.goto(`/checklist/${PROGRAM_ID}`);
    await page.getByRole("button", { name: "Review for this programme" }).click();
    await expect(page.getByRole("button", { name: "Reviewing 0 of 5" })).toBeVisible();

    await page.getByRole("link", { name: "Dashboard", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await page.waitForTimeout(1000);
    await page.goBack();

    await expect(page).toHaveURL(new RegExp(`/checklist/${PROGRAM_ID}$`));
    await expect(page.getByText("Partial fit 83/100")).toBeVisible();
    await expect(page.getByText("Lead with your strongest relevant project")).toBeVisible();
  });

  test("a free account sees the upgrade dialog from the checklist", async ({ page }) => {
    await mockChecklist(page);
    await page.route(`${CV_API_BASE}/latest`, (route) =>
      route.fulfill(withCors(READY_CV)),
    );
    await page.route(`${CV_API_BASE}/review`, (route) =>
      route.fulfill(withCors({ error: "subscription_required" }, 403)),
    );

    await page.goto(`/checklist/${PROGRAM_ID}`);
    await page.getByRole("button", { name: "Review for this programme" }).click();

    await expect(
      page.getByRole("heading", { name: "CV review is part of Dalil Pro" }),
    ).toBeVisible();
  });
});

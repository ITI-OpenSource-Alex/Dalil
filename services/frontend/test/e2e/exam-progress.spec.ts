import { test, expect, Page } from "./fixtures/auth";

const GATEWAY = "http://localhost:8080";

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

const PROFILE = {
  id: "user-1",
  email: "amina.hassan@example.com",
  subscriptionTier: "pro",
  isVerified: true,
  profile: {
    userId: "user-1",
    degreeLevel: "Bachelors",
    gpa: 3.2,
    gpaScale: "4.0",
    ieltsScore: 7.0,
    ieltsListening: 7.0,
    ieltsReading: 7.0,
    ieltsWriting: 7.0,
    ieltsSpeaking: 7.0,
    targetCountries: ["Germany"],
    fieldOfStudy: "Computer Science",
    ects: 180,
    workExperienceYears: 1,
    extracurricularsScore: 5,
  },
};

async function mockProfile(page: Page) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(withCors(PROFILE)),
  );
  // Profile page also mounts CV + opportunities; stub so they don't block the tab.
  await page.route(`${GATEWAY}/api/writing/cv/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [] })),
  );
}

async function openExamProgress(page: Page) {
  await page.goto("/profile");
  await page.getByRole("tab", { name: "Exam Progress" }).click();
}

test("empty state shows Start your first practice exam CTA", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(withCors({})),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(withCors([])),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({})),
  );

  await openExamProgress(page);

  const cta = page.getByTestId("exam-progress-empty-cta");
  await expect(cta).toHaveText("Start your first practice exam");
  await expect(cta).toHaveAttribute("href", "/exam");
});

test("one Reading score appears after opening Exam Progress", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({
        reading: [{ date: "2026-03-01T00:00:00Z", band: 6.5 }],
      }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(
      withCors([
        {
          sessionId: "11111111-1111-1111-1111-111111111111",
          skill: "reading",
          examType: "academic",
          bandScore: 6.5,
          date: "2026-03-01T00:00:00Z",
        },
      ]),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({ reading: "Section 3" })),
  );

  await openExamProgress(page);

  await expect(page.getByText("6.5").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "View Results" })).toHaveAttribute(
    "href",
    "/exam/results?session=11111111-1111-1111-1111-111111111111&skill=Reading",
  );
});

test("two Reading bands appear in chronological order", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({
        reading: [
          { date: "2026-01-01T00:00:00Z", band: 6.0 },
          { date: "2026-02-01T00:00:00Z", band: 7.0 },
        ],
      }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(withCors([])),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({})),
  );

  await openExamProgress(page);
  // Skill pills are Radix TabsTrigger → role="tab"
  await page.getByRole("tab", { name: "Reading" }).click();

  const points = page.locator("[data-testid^=trend-point-]");
  await expect(points).toHaveCount(2);
  await expect(points.nth(0)).toContainText("6.0");
  await expect(points.nth(1)).toContainText("7.0");
});

test("weak-areas failure still shows progress content", async ({ page }) => {
  await mockProfile(page);
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      withCors({ reading: [{ date: "2026-03-01T00:00:00Z", band: 6.0 }] }),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/history**`, (route) =>
    route.fulfill(
      withCors([
        {
          sessionId: "22222222-2222-2222-2222-222222222222",
          skill: "reading",
          examType: "academic",
          bandScore: 6.0,
          date: "2026-03-01T00:00:00Z",
        },
      ]),
    ),
  );
  await page.route(`${GATEWAY}/api/exam/weak-areas`, (route) =>
    route.fulfill(withCors({ error: "boom" }, 500)),
  );

  await openExamProgress(page);
  await expect(page.getByText("6.0").first()).toBeVisible();
  await expect(page.getByText("Weak areas unavailable")).toBeVisible();
});

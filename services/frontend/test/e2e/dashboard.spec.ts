import { test, expect, Page } from "./fixtures/auth";

// Dashboard widgets (Phase E, docs/IA-REDESIGN-PROPOSAL.md) each call the
// Gateway (localhost:8080) directly, a different origin than the frontend
// (localhost:3000) -- same CORS reasoning as speaking-history-mocked.spec.ts.
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
  subscriptionTier: "free",
  isVerified: true,
  profile: {
    userId: "user-1",
    degreeLevel: "Bachelors",
    gpa: 3.8,
    ieltsScore: null as number | null,
    targetCountries: ["Germany"],
    fieldOfStudy: "Computer Science",
    ects: 180,
    workExperienceYears: 0,
    extracurricularsScore: 0,
    gpaScale: "4.0",
  },
};

async function mockEmptyDashboardData(page: Page, profile = PROFILE) {
  await page.route(`${GATEWAY}/api/profile`, (route) => route.fulfill(withCors(profile)));
  await page.route(`${GATEWAY}/api/speaking/sessions`, (route) => route.fulfill(withCors([])));
  await page.route(`${GATEWAY}/api/writing/essays*`, (route) => route.fulfill(withCors([])));
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(withCors({ error: "subscription_required", upgradeUrl: "/#pricing" }, 403)),
  );
}

test.describe("GOA Dashboard", () => {
  test("greets the signed-in user and shows every widget's empty state for a brand-new account", async ({
    page,
  }) => {
    await mockEmptyDashboardData(page);

    await page.goto("/dashboard");

    await expect(page.getByText(/Welcome back, Amina Hassan/)).toBeVisible();
    await expect(page.getByText("No practice sessions yet")).toBeVisible();
    await expect(page.getByText("IELTS scoring is part of GOA Pro")).toBeVisible();
    // Recommendations only render once there's exam data to derive a real
    // suggestion from -- a Free account never sees it.
    await expect(page.getByText("Recommended for you")).toHaveCount(0);
  });

  test("shows recent activity merged from Speaking and Writing, most recent first", async ({
    page,
  }) => {
    await page.route(`${GATEWAY}/api/profile`, (route) => route.fulfill(withCors(PROFILE)));
    await page.route(`${GATEWAY}/api/speaking/sessions`, (route) =>
      route.fulfill(
        withCors([
          {
            id: "s1",
            question_prompt: "Describe a memorable journey",
            question_type: "part2",
            overall_band: 6.5,
            created_at: "2026-01-01T00:00:00Z",
          },
        ]),
      ),
    );
    await page.route(`${GATEWAY}/api/writing/essays*`, (route) =>
      route.fulfill(
        withCors([
          {
            id: 1,
            submitted_at: "2026-01-02T00:00:00Z",
            status: "evaluated",
            submission_type: "practice",
            exam_type: null,
            task_number: null,
            overall_band: 7.0,
            excerpt: "Technology has changed education significantly.",
          },
        ]),
      ),
    );
    await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
      route.fulfill(withCors({ error: "subscription_required" }, 403)),
    );

    await page.goto("/dashboard");

    const activity = page.locator("li", { hasText: "Technology has changed education" });
    await expect(activity).toBeVisible();
    // The essay (Jan 2) is more recent than the speaking session (Jan 1), so
    // it must render first.
    const firstItem = page.locator("ul > li").first();
    await expect(firstItem).toContainText("Technology has changed education");
  });

  test("Quick Actions links reach every major section", async ({ page }) => {
    await mockEmptyDashboardData(page);

    await page.goto("/dashboard");

    // Scoped to <main>: the sidebar (an <aside>, not <main>) has its own
    // "CV Review" and "Speaking Practice" links, so an unscoped getByRole
    // here would match two elements and fail Playwright's strict mode.
    const main = page.getByRole("main");
    await expect(main.getByRole("link", { name: "CV Review" })).toHaveAttribute(
      "href",
      "/cv-review",
    );
    await expect(main.getByRole("link", { name: "Speaking Practice" })).toHaveAttribute(
      "href",
      "/practice/speaking",
    );
  });

  test("a completed profile shows full progress and no completion nudge", async ({ page }) => {
    const completeProfile = {
      ...PROFILE,
      profile: { ...PROFILE.profile, ieltsScore: 7.0 },
    };
    await mockEmptyDashboardData(page, completeProfile);

    await page.goto("/dashboard");

    await expect(page.getByText("5 of 5 fields")).toBeVisible();
    await expect(page.getByRole("link", { name: "Complete your profile" })).toHaveCount(0);
  });
});

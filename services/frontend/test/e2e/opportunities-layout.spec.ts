import { test, expect } from "./fixtures/auth";

const PROGRAMMES = [
  [
    "computer-science",
    "Computer Science",
    "Gisma University of Applied Sciences",
    100,
  ],
  [
    "informatics-business",
    "Informatics and Business",
    "South Westphalia University of Applied Sciences",
    99,
  ],
  [
    "information-engineering",
    "Information Engineering and Computer Science",
    "Rhine-Waal University of Applied Sciences and International Research Institute",
    99,
  ],
] as const;

test("programme cards stay equal-width and truncate long text", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route("**/api/profile", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "layout-user",
        email: "layout@example.com",
        subscriptionTier: "paid",
        isVerified: true,
        profile: {
          userId: "layout-user",
          degreeLevel: "bachelor",
          gpa: 3.8,
          ieltsScore: 7,
          targetCountries: ["Germany"],
          fieldOfStudy: "Computer Science",
          ects: 180,
          workExperienceYears: 1,
          extracurricularsScore: 0,
          gpaScale: "4.0",
        },
      }),
    }),
  );
  await page.route("**/api/chat/sessions/*/history", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/opportunities/query", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        programs: PROGRAMMES.map(([programId, programName, university, score]) => ({
          programId,
          programName,
          university,
          country: "Germany",
          deadline: null,
          sourceUrl: `https://example.edu/${programId}`,
          dataSource: "scraped",
          result: {
            score,
            requirements_evaluated: 3,
            requirements_met: 3,
            blocked_by: null,
            score_breakdown: {
              eligibility_points: 40,
              requirement_headroom_points: score - 85,
              subject_points: 35,
              destination_points: 10,
              headroom_dimensions_evaluated: 3,
              confidence: "standard",
              subject_relevance: 1,
              total: score,
            },
          },
        })),
      }),
    }),
  );

  await page.goto("/opportunities");
  const cells = page.getByTestId("opportunity-card-cell");
  await expect(cells).toHaveCount(3);

  const widths = await cells.evaluateAll((items) =>
    items.map((item) => Math.round(item.getBoundingClientRect().width)),
  );
  expect(new Set(widths).size).toBe(1);
  expect(widths[0]).toBeGreaterThan(340);

  const longUniversity = page
    .getByTestId("opportunity-university")
    .filter({ hasText: "Rhine-Waal" });
  await expect(longUniversity).toHaveAttribute(
    "title",
    PROGRAMMES[2][2],
  );
  expect(
    await longUniversity.evaluate(
      (element) => element.scrollWidth > element.clientWidth,
    ),
  ).toBe(true);

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);

  await page.screenshot({
    path: testInfo.outputPath("programme-card-grid.png"),
    fullPage: false,
  });
});

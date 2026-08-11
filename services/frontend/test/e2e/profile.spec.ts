import { test, expect, Page } from "./fixtures/auth";
import type { CurrentUser, UserProfileDetail } from "@/app/types/profile";

const GATEWAY = "http://localhost:8080";
const CV_API_BASE = `${GATEWAY}/api/writing/cv`;

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

const BASE_PROFILE_DETAIL: UserProfileDetail = {
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
};

const BASE_PROFILE: CurrentUser = {
  id: "user-1",
  email: "amina.hassan@example.com",
  subscriptionTier: "free",
  isVerified: true,
  profile: BASE_PROFILE_DETAIL,
};

async function mockProfileGet(page: Page, profile: CurrentUser = BASE_PROFILE) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(withCors(profile)),
  );
}

test("profile autosaves GPA on blur and persists after refresh", async ({
  page,
}) => {
  let storedGpa = 3.2;
  const profile = () => ({
    id: "user-1",
    email: "amina.hassan@example.com",
    subscriptionTier: "free",
    isVerified: true,
    profile: {
      userId: "user-1",
      degreeLevel: "Bachelors",
      gpa: storedGpa,
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
  });

  await page.route(`${GATEWAY}/api/profile`, async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      if (typeof body.gpa === "number") storedGpa = body.gpa;
      await route.fulfill(withCors({ ok: true }));
      return;
    }
    await route.fulfill(withCors(profile()));
  });
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [] })),
  );

  await page.goto("/profile?tab=edit");
  const gpa = page.getByLabel(/^GPA$/i);
  await gpa.fill("3.9");
  await gpa.blur();
  await page.waitForTimeout(2000);
  await page.reload();
  await expect(page.getByLabel(/^GPA$/i)).toHaveValue("3.9");
});

test("CV upload on profile shows Processing then ready filename", async ({
  page,
}) => {
  let cvReady = false;

  await mockProfileGet(page);
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [] })),
  );
  await page.route(`${CV_API_BASE}/latest`, (route) => {
    if (cvReady) {
      return route.fulfill(
        withCors({
          cvId: 1,
          s3Key: "cvs/user-1/resume.pdf",
          originalFilename: "resume.pdf",
          status: "ready",
          uploadedAt: "2026-01-01T00:00:00Z",
        }),
      );
    }
    return route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404));
  });
  await page.route(`${CV_API_BASE}/upload`, (route) =>
    route.fulfill(
      withCors(
        { cvId: 1, status: "processing", s3Key: "cvs/user-1/resume.pdf" },
        200,
      ),
    ),
  );

  await page.goto("/profile?tab=edit");
  await page.locator('input[type="file"]').setInputFiles({
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\nresume\n%%EOF"),
  });

  await expect(page.getByText("resume.pdf")).toBeVisible();
  await expect(page.getByText(/Processing/)).toBeVisible();

  cvReady = true;
  await expect(page.getByText("Ready for review")).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText("resume.pdf")).toBeVisible();
  await expect(page.getByText(/Processing/)).toHaveCount(0);
});

test("opportunity matches show score bar and open detail modal", async ({
  page,
}) => {
  const matchedProgram = {
    programId: "prog-tum-cs",
    programName: "MSc Computer Science",
    university: "TU Munich",
    country: "Germany",
    deadline: "2026-12-01",
    sourceUrl: "https://www.mastersportal.com/studies/123/example.html",
    dataSource: "scraped",
    requirements: {
      minEcts: 180,
      minGpa: 3.0,
      minIelts: 6.5,
      degreeLevel: "Bachelors",
      minWorkExperience: null,
    },
    result: {
      score: 85,
      requirements_evaluated: 4,
      requirements_met: 4,
      score_breakdown: {
        eligibility_points: 40,
        requirement_headroom_points: 0,
        subject_points: 35,
        destination_points: 10,
        headroom_dimensions_evaluated: 3,
        confidence: "standard",
        subject_relevance: 1,
        total: 85,
      },
      blocked_by: null,
      gap_report: {
        ielts: {
          message: "Raise IELTS overall to 7.0 for a stronger match.",
        },
      },
    },
  };

  await mockProfileGet(page);
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [matchedProgram] })),
  );

  await page.goto("/profile");

  await expect(page.getByText("85% fit")).toBeVisible();
  await expect(page.getByText("Exact intended-field match")).toBeVisible();
  await expect(
    page.getByText(
      "Score: 40 eligibility + 0 requirement headroom + 35 subject fit + 10 destination fit",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Source listing" }),
  ).toHaveAttribute(
    "href",
    "https://www.mastersportal.com/studies/123/example.html",
  );
  await expect(
    page.getByText("Possible match against your profile"),
  ).toBeVisible();

  await page
    .getByRole("button", {
      name: /View details for MSc Computer Science at TU Munich/i,
    })
    .click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Requirements", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Min IELTS")).toBeVisible();
  await expect(dialog.getByText("6.5")).toBeVisible();
  await expect(dialog.getByText("Gap report")).toBeVisible();
  await expect(
    dialog.getByText("Raise IELTS overall to 7.0 for a stronger match."),
  ).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Apply" })).toHaveAttribute(
    "href",
    "/checklist/prog-tum-cs",
  );
});

test("a missing detail jumps to the section that owns it", async ({ page }) => {
  await mockProfileGet(page, {
    ...BASE_PROFILE,
    profile: { ...BASE_PROFILE_DETAIL, ects: null },
  });
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) =>
    route.fulfill(withCors({ programs: [] })),
  );

  await page.goto("/profile");
  await page.getByRole("button", { name: "Add ECTS credits" }).click();

  await expect(page.getByRole("tab", { name: "Edit profile" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByLabel("ECTS credits")).toBeVisible();
  await expect(page).toHaveURL(/\?tab=edit/);
});

test("editing the profile re-ranks matches when you return to them", async ({
  page,
}) => {
  let searches = 0;

  await page.route(`${GATEWAY}/api/profile`, async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill(withCors({ ok: true }));
      return;
    }
    await route.fulfill(withCors(BASE_PROFILE));
  });
  await page.route(`${CV_API_BASE}/latest`, (route) =>
    route.fulfill(withCors({ detail: "No CV uploaded yet" }, 404)),
  );
  await page.route(`${GATEWAY}/api/opportunities/query`, (route) => {
    searches += 1;
    return route.fulfill(withCors({ programs: [] }));
  });

  await page.goto("/profile");
  await expect(page.getByText("No programmes matched yet")).toBeVisible();
  expect(searches).toBe(1);

  await page.getByRole("tab", { name: "Edit profile" }).click();
  const gpa = page.getByLabel("GPA");
  await gpa.fill("3.9");
  await gpa.blur();
  await expect(page.getByText("Saved")).toBeVisible();

  // Flicking to a third tab must not spend a search.
  await page.getByRole("tab", { name: "Exam Progress" }).click();
  expect(searches).toBe(1);

  await page.getByRole("tab", { name: "Matches" }).click();
  await expect.poll(() => searches).toBe(2);
});

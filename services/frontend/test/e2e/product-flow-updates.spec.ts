import { test, expect } from "./fixtures/auth";

const GATEWAY = "http://localhost:8080";
const cors = (body: unknown) => ({
  status: 200,
  contentType: "application/json",
  headers: {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Credentials": "true",
  },
  body: JSON.stringify(body),
});

const paidProfile = {
  id: "user-1",
  email: "student@example.com",
  subscriptionTier: "paid",
  isVerified: true,
  profile: {
    userId: "user-1",
    degreeLevel: "Bachelors",
    gpa: 3.4,
    gpaScale: "4.0",
    ieltsScore: 7,
    targetCountries: ["Germany"],
    fieldOfStudy: "Computer Science",
    ects: 180,
    workExperienceYears: 1,
    extracurricularsScore: 0,
  },
};

test("Practice navigation exposes only speaking and writing; history lives in each page", async ({
  page,
}) => {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(cors(paidProfile)),
  );
  await page.goto("/practice/speaking");
  const aside = page.locator("aside");
  await expect(
    aside.getByRole("link", { name: "Speaking Practice" }),
  ).toBeVisible();
  await expect(
    aside.getByRole("link", { name: "Writing Practice" }),
  ).toBeVisible();
  await expect(
    aside.getByRole("link", { name: "Speaking History" }),
  ).toHaveCount(0);
  await expect(
    aside.getByRole("link", { name: "Writing History" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("main").getByRole("link", { name: "View history" }),
  ).toHaveAttribute("href", "/practice/speaking/history");
});

test("Speaking exam is shipped and opens the full interviewer", async ({
  page,
}) => {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(cors(paidProfile)),
  );
  await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
    route.fulfill(
      cors({ reading: [], listening: [], writing: [], speaking: [] }),
    ),
  );
  await page.goto("/exam");
  const speakingCard = page.locator(".rounded-3xl").filter({
    has: page.getByRole("heading", { name: "Speaking", exact: true }),
  });
  const speakingButton = speakingCard.getByRole("button", {
    name: "Take Exam",
  });
  await expect(speakingButton).toBeEnabled();
  await speakingButton.click();
  await expect(page).toHaveURL(/\/practice\/speaking\?mode=exam$/);
});

test("Programme detail shows source, complete requirements and visa facts", async ({
  page,
}) => {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(cors(paidProfile)),
  );
  await page.route(`${GATEWAY}/api/opportunities/program-1`, (route) =>
    route.fulfill(
      cors({
        programId: "program-1",
        programName: "MSc Computer Science",
        university: "TU Berlin",
        country: "Germany",
        deadline: "2027-01-15",
        sourceUrl: "https://university.example/program",
        discipline: "computer_science",
        requirements: {
          minEcts: 180,
          minGpa: 3,
          minIelts: 6.5,
          degreeLevel: "Master",
          minWorkExperience: 1,
          requiredCitizenship: null,
        },
        result: { score: 100, blocked_by: null, gap_report: {} },
        visaRequirements: [
          {
            visa_type: "Student visa",
            issuing_body: "German mission",
            requirements: { passport: true, admission_letter: true },
            proof_of_funds: { amount: "11904 EUR" },
            source_url: "https://government.example/visa",
            processing_days_min: 30,
            processing_days_max: 60,
            notes: null,
            last_verified_at: "2026-08-01T00:00:00Z",
          },
        ],
      }),
    ),
  );
  await page.goto("/opportunities/program-1");
  await expect(
    page.getByRole("heading", { name: "MSc Computer Science" }),
  ).toBeVisible();
  await expect(page.getByText("100% fit", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open source programme listing" }),
  ).toHaveAttribute("href", "https://university.example/program");
  await expect(page.getByText("11904 EUR")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Official visa source" }),
  ).toHaveAttribute("href", "https://government.example/visa");
});

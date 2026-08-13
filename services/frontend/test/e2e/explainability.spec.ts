import { test, expect, type Page } from "./fixtures/auth";

const GATEWAY = "http://localhost:8080";

function cors(body: unknown, status = 200) {
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

async function mockChatShell(page: Page) {
  await page.route(`${GATEWAY}/api/profile`, (route) =>
    route.fulfill(
      cors({
        id: "explain-user",
        email: "student@example.com",
        subscriptionTier: "paid",
        isVerified: true,
        profile: null,
      }),
    ),
  );
  await page.route("**/api/chat/sessions/*/history", (route) =>
    route.fulfill(cors([])),
  );
}

async function expectEditableExplanation(
  page: Page,
  kind: string,
  promptText: RegExp,
) {
  await page.locator(`[data-explanation-kind="${kind}"]`).first().click();
  await expect(page.getByTestId("dalil-chat-panel")).toBeVisible();
  await expect(page.getByTestId("explanation-context-card")).toBeVisible();
  const input = page.getByTestId("chat-input");
  await expect(input).toHaveValue(promptText);
  await expect(input).toBeFocused();
  await expect(page.getByTestId("user-message")).toHaveCount(0);

  const edited = `My own ${kind} follow-up question`;
  await input.fill(edited);
  await expect(input).toHaveValue(edited);
}

test.describe("Ask Dalil explainability entry points", () => {
  test.beforeEach(async ({ page }) => {
    await mockChatShell(page);
  });

  test("dashboard supports score and recommendation questions", async ({ page }, testInfo) => {
    await page.route(`${GATEWAY}/api/speaking/sessions`, (route) =>
      route.fulfill(cors([])),
    );
    await page.route(`${GATEWAY}/api/writing/essays*`, (route) =>
      route.fulfill(cors([])),
    );
    await page.route(`${GATEWAY}/api/exam/progress`, (route) =>
      route.fulfill(
        cors({
          reading: [{ date: "2026-08-01", band: 7.5 }],
          listening: [{ date: "2026-08-02", band: 7 }],
          speaking: [{ date: "2026-08-03", band: 6 }],
          writing: [{ date: "2026-08-04", band: 6.5 }],
        }),
      ),
    );

    await page.goto("/dashboard");
    await expectEditableExplanation(page, "exam_score", /latest Reading band 7\.5/i);
    await page.getByRole("button", { name: "Close Dalil chat" }).click();
    await expectEditableExplanation(page, "recommendation", /recommending Speaking practice/i);
    const panel = page.getByTestId("dalil-chat-panel");
    await panel.evaluate((element) =>
      Promise.all(element.getAnimations().map((animation) => animation.finished)),
    );
    await expect
      .poll(async () => (await page.getByTestId("explanation-context-card").boundingBox())?.height ?? 0)
      .toBeGreaterThan(48);
    await expect
      .poll(async () => (await page.getByTestId("chat-input").boundingBox())?.height ?? 999)
      .toBeLessThan(80);
    await page.screenshot({
      path: testInfo.outputPath("ask-dalil-desktop.png"),
      fullPage: false,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(panel).toBeVisible();
    await panel.evaluate((element) =>
      Promise.all(element.getAnimations().map((animation) => animation.finished)),
    );
    await page.screenshot({
      path: testInfo.outputPath("ask-dalil-mobile.png"),
      fullPage: false,
    });
  });

  test("writing, speaking and CV feedback each attach their own evidence", async ({
    page,
  }) => {
    await page.route("**/api/writing/essays/upload", (route) =>
      route.fulfill(cors({ id: 1, status: "ready" })),
    );
    await page.route("**/api/writing/essays/1/evaluate", (route) =>
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'data: {"type":"criterion","criterion":"grammar","band":6.5,"feedback":"Sentence control is inconsistent"}',
          "",
          'data: {"type":"complete","essay_id":"1","overall_band":6.5,"evaluations":{"grammar":{"band":6.5,"feedback":"Sentence control is inconsistent"}}}',
          "",
        ].join("\n"),
      }),
    );

    await page.goto("/practice/writing");
    await page.getByTestId("essay-input").fill("Technology changes education in many ways.");
    await page.getByTestId("submit-essay-button").click();
    await expect(page.getByText("Estimated Overall Band")).toBeVisible();
    await expectEditableExplanation(
      page,
      "writing_score",
      /Grammatical Range & Accuracy receive band 6\.5/i,
    );
    await page.getByRole("button", { name: "Close Dalil chat" }).click();

    const speakingId = "11111111-1111-1111-1111-111111111111";
    await page.route(`${GATEWAY}/api/speaking/sessions/${speakingId}`, (route) =>
      route.fulfill(
        cors({
          id: speakingId,
          question_prompt: "Describe a memorable journey.",
          question_type: "part2",
          transcript: "I travelled with my family.",
          overall_band: 7,
          created_at: "2026-08-01T10:00:00Z",
          evaluation: {
            "Fluency and Coherence": { band: 7, feedback: "Good pacing." },
            "Lexical Resource": { band: 6.5, feedback: "Some repetition." },
            "Grammatical Range and Accuracy": { band: 7, feedback: "Good range." },
            Pronunciation: { band: 7, feedback: "Clear speech." },
          },
        }),
      ),
    );
    await page.goto(`/practice/speaking/history/${speakingId}`);
    await expectEditableExplanation(page, "speaking_score", /Speaking band 7/i);
    await page.getByRole("button", { name: "Close Dalil chat" }).click();

    const cvBase = `${GATEWAY}/api/writing/cv`;
    await page.route(`${cvBase}/latest`, (route) =>
      route.fulfill(
        cors({
          cvId: 8,
          s3Key: "cvs/explain-user/resume.pdf",
          originalFilename: "resume.pdf",
          status: "ready",
          uploadedAt: "2026-08-01T00:00:00Z",
        }),
      ),
    );
    await page.route(`${cvBase}/review`, (route) =>
      route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Access-Control-Allow-Origin": "http://localhost:3000",
          "Access-Control-Allow-Credentials": "true",
        },
        body: [
          'event: complete\ndata: {"overallScore":72,"sections":[{"name":"Experience","score":65,"issues":["Impact is not quantified"],"suggestions":["Add measurable outcomes"]}]}',
          "",
        ].join("\n"),
      }),
    );
    await page.goto("/cv-review");
    await page.getByLabel("Target country").fill("Germany");
    await page.getByLabel("Target field of study").fill("Computer Science");
    await page.getByRole("button", { name: "Start CV Review" }).click();
    await expect(page.getByText("Overall score 72/100")).toBeVisible();
    await expectEditableExplanation(page, "cv_review", /CV receive 72\/100/i);
  });

  test("checklist and official visa questions remain visibly source-bound", async ({
    page,
  }) => {
    await page.route(
      `${GATEWAY}/api/checklists/demo-program/financial`,
      (route) =>
        route.fulfill(
          cors({
            programId: "demo-program",
            items: [
              {
                type: "proof_of_funds",
                country: "Germany",
                issuingBody: "Federal Foreign Office",
                message: "Show sufficient funds for the study period.",
                sourceUrl: "https://www.auswaertiges-amt.de/",
                lastVerifiedAt: "2026-07-01T00:00:00Z",
              },
            ],
          }),
        ),
    );
    await page.route(`${GATEWAY}/api/checklists/demo-program`, (route) =>
      route.fulfill(
        cors({
          checklistId: "checklist-1",
          programId: "demo-program",
          generatedBy: "llm",
          items: [
            {
              itemId: "language-certificate",
              title: "Prepare language certificate",
              description: "Upload proof of the required language level.",
              category: "language",
              checked: false,
            },
          ],
        }),
      ),
    );

    await page.goto("/checklist/demo-program");
    await expectEditableExplanation(page, "checklist", /language certificate/i);
    await page.getByRole("button", { name: "Close Dalil chat" }).click();
    await expectEditableExplanation(page, "visa_requirement", /financial requirement for Germany/i);
    await expect(page.getByTestId("explanation-context-card")).toContainText(
      "Germany financial requirement",
    );
  });
});

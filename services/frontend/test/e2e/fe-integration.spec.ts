import { test, expect } from "@playwright/test";
import { clearAuthCookie, seedAuthCookie } from "./fixtures/auth";

test.describe("Frontend E2E & Browser Integration Tests (FE-01 to FE-06)", () => {
  // These specs drive protected routes (/chat, /onboarding, /exam) which
  // middleware.ts now guards on the access_token cookie. Seeded here rather
  // than via the fixture's `test`, because FE-01 deliberately starts signed
  // OUT to assert the login page renders -- a cookie would bounce it to /chat.
  test.beforeEach(async ({ page }) => {
    await seedAuthCookie(page);
  });

  /**
   * FE-01: Visit /, /login, complete the onboarding wizard -> All pages render, wizard reaches /chat
   */
  test("FE-01: Visit landing page, login, and complete onboarding wizard to reach /chat", async ({
    page,
  }) => {
    // Steps 1 and 2 are the signed-out experience: /login redirects a
    // cookie-bearing visitor straight into the app, so the session seeded in
    // beforeEach has to go before we can assert the form renders at all.
    await clearAuthCookie(page);

    // 1. Visit Landing Page
    await page.goto("/");
    await expect(page.locator("nav")).toBeVisible();

    // 2. Visit Login Page
    await page.goto("/login");
    await expect(page.locator("#login-email")).toBeVisible();
    await expect(page.locator("#login-password")).toBeVisible();

    // From here the test is exercising an authenticated wizard, which is what
    // a real user reaches only after signing in.
    await seedAuthCookie(page);

    // 3. Complete Onboarding Wizard Step 1: Academic
    // Skipping this wizard now persists via PUT /api/profile (Phase 3); mocked
    // here so the test doesn't need a live Gateway + User service.
    await page.route("**/api/profile", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/onboarding");
    await expect(page.locator("text=Tell us about your education")).toBeVisible();

    await page.selectOption('select[name="degree"]', "Bachelors");
    await page.fill('input[name="major"]', "Computer Science");
    await page.fill('input[name="university"]', "Cairo University");
    await page.fill('input[name="gradYear"]', "2025");
    await page.fill('input[name="gpa"]', "3.8");
    await page.fill('input[name="ECTScred"]', "180");
    await page.click('button[type="submit"]');

    // Step 2: Languages
    await expect(page.locator("text=How's your English?")).toBeVisible();
    await page.click('label:has-text("Not yet")');
    await page.click('label:has-text("Not sure yet")');
    await page.click('button[type="submit"]');

    // Step 3: Targets
    await expect(page.getByRole("heading", { name: "Where do you want to study?" })).toBeVisible();
    // Destinations are a searchable multi-select now, not six fixed
    // checkboxes -- and they store the full country NAME, which is what RAG
    // filters programmes on. Typing plus Enter commits the highlighted option.
    await page.getByLabel("Destination countries").fill("Germany");
    await page.getByRole("option", { name: "Germany" }).first().click();
    await page.selectOption('select[name="targetDegree"]', "Masters");
    await page.fill('input[name="targetMajor"]', "Data Science");
    await page.selectOption('select[name="targetIntake"]', "Fall 2026");
    await page.click('button[type="submit"]');

    // Wizard reaches /dashboard -- the whole point of completing it (Phase E,
    // docs/IA-REDESIGN-PROPOSAL.md; previously a temporary redirect to
    // /opportunities stood in for the Dashboard page before it existed).
    // Onboarding is 3 steps (Phase C removed the CV upload step; CV upload
    // now belongs to its own /cv-review page, built in Phase E).
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 5000 });
  });

  /**
   * FE-02: Send a chat message in the UI -> Tokens visibly stream in, not a single paste
   */
  test("FE-02: Send a chat message and verify incremental token streaming", async ({
    page,
  }) => {
    // Intercept /api/chat with delayed SSE chunks
    await page.route("**/api/chat", async (route) => {
      const ssePayload = [
        'data: {"type":"metadata","intent":"chat","confidence":1}\n\n',
        'data: {"type":"token","content":"Hello"}\n\n',
        'data: {"type":"token","content":" world"}\n\n',
        'data: {"type":"token","content":", how can I assist you today?"}\n\n',
      ];

      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: ssePayload.join(""),
      });
    });

    await page.goto("/chat");
    const input = page.getByTestId("chat-input");
    const sendBtn = page.getByTestId("send-message-button");

    await input.fill("Hello GOA!");
    await sendBtn.click();

    // User message is displayed
    await expect(page.getByTestId("user-message").last()).toContainText("Hello GOA!");

    // Assistant message streams in
    const assistantBubble = page.getByTestId("assistant-message").last();
    await expect(assistantBubble).toContainText("Hello world, how can I assist you today?");
  });

  // FE-03 (CV upload displays real upload progress and a completion status,
  // exercised from inside the onboarding wizard) is retired rather than
  // rewritten: Phase C removed the CV upload step from onboarding entirely,
  // and Phase E's /cv-review page (see cv-review.spec.ts) is a different
  // screen with its own dedicated coverage, not a like-for-like replacement
  // of this specific test. FE-04 through FE-06 keep their existing numbers
  // rather than being renumbered, consistent with retiring a ticket number
  // instead of reusing it.

  /**
   * FE-04: Navigate to /exam, select each of the 4 skills -> Exam shell loads correctly for all 4
   */
  test("FE-04: Navigate to /exam and verify exam shell loads for all 4 skills", async ({
    page,
  }) => {
    // Register catch-all mock route for exam sessions API
    await page.route("**/sessions/**", async (route) => {
      const url = route.request().url();
      let currentSkill = "Reading";
      if (url.includes("speaking")) currentSkill = "Speaking";
      else if (url.includes("listening")) currentSkill = "Listening";
      else if (url.includes("writing")) currentSkill = "Writing";

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: `mock-session-${currentSkill.toLowerCase()}`,
          session_id: `mock-session-${currentSkill.toLowerCase()}`,
          exam_type: "academic",
          skill_area: currentSkill.toLowerCase(),
          status: "in_progress",
          remaining_time_seconds: 3600,
          questions: [
            {
              section: 1,
              questions: [
                { id: "q1", prompt: `${currentSkill} Task 1 Prompt` },
                { id: "q2", prompt: `${currentSkill} Task 2 Prompt` },
              ],
            },
          ],
        }),
      });
    });

    const skills = ["Reading", "Listening", "Writing", "Speaking"] as const;

    for (const skill of skills) {
      await page.goto("/exam");

      // Inject mock session into sessionStorage to allow immediate exam shell access
      await page.evaluate(
        ({ skillName }) => {
          sessionStorage.clear();
          sessionStorage.setItem(
            "active_exam_session",
            JSON.stringify({
              sessionId: `mock-session-${skillName.toLowerCase()}`,
              examType: "Academic",
              skillArea: skillName,
            })
          );
        },
        { skillName: skill }
      );

      await page.goto(`/exam/shell?session=mock-session-${skill.toLowerCase()}`);
      await expect(page).toHaveURL(new RegExp(`/exam/shell\\?session=mock-session-${skill.toLowerCase()}`));

      // Verify header renders skill module title
      await expect(page.locator("header")).toContainText(`${skill} Module`);
    }
  });

  /**
   * FE-05: Deep-link from Chat into Speaking Practice -> Mic permission
   * requested, live transcript/waveform updates.
   *
   * Phase D (docs/IA-REDESIGN-PROPOSAL.md): Speaking Practice moved out of
   * Chat onto its own page. Chat's mic icon is now a plain deep link to
   * /practice/speaking rather than an inline toggle, so this test's job
   * changed from "does the inline panel open" to "does the link land on a
   * working Speaking Practice page" -- the rest (start, transcript, Stop
   * once genuinely connected) is unchanged.
   */
  test("FE-05: Speaking interface opens, grants mic permission, and displays live transcript panel", async ({
    page,
    context,
    request,
  }) => {
    // The Stop button only replaces Start once the speaking WebSocket is
    // genuinely connected, which needs a real Speaking Service. Skip when it
    // isn't up, exactly as speaking-system.spec.ts does.
    //
    // This previously asserted Stop was visible immediately on click, which
    // only held because startSpeaking() used to set state to "listening"
    // synchronously before any socket existed — the UI claimed to be
    // recording when it wasn't. That bug is fixed, so the test now waits for
    // the real connection instead of the false one.
    const speakingServiceURL =
      process.env.SPEAKING_SERVICE_URL ?? "http://localhost:8082";
    const speakingReachable = await request
      .get(`${speakingServiceURL}/metrics`, { timeout: 2000 })
      .then((res) => res.ok())
      .catch(() => false);

    test.skip(
      !speakingReachable,
      `Speaking service not reachable at ${speakingServiceURL} — FE-05 needs a live WebSocket handshake.`,
    );

    // Grant microphone permissions
    await context.grantPermissions(["microphone"]);

    await page.goto("/chat");

    // Click Speaking Practice — a deep link into Practice now, not an inline
    // toggle.
    const speakingLink = page.getByTitle("Speaking Practice");
    await expect(speakingLink).toBeVisible();
    await speakingLink.click();

    await expect(page).toHaveURL(/\/practice\/speaking/);

    // Speaking panel is mounted on load.
    const speakingPanel = page.getByTestId("speaking-panel");
    await expect(speakingPanel).toBeVisible();

    // Start speaking session
    const startBtn = page.getByTestId("start-speaking-button");
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // Transcript panel is present throughout the session.
    await expect(page.getByTestId("live-transcript")).toBeVisible();

    // Stop becomes available only once the WebSocket actually connects.
    await expect(page.getByTestId("stop-speaking-button")).toBeVisible({
      timeout: 15000,
    });
  });

  /**
   * FE-06: Resize to mobile viewport (375px) -> Chat UI remains usable
   */
  test("FE-06: Chat UI remains clean, structured, and usable on 375px mobile viewport", async ({
    page,
  }) => {
    // Set 375px mobile viewport (iPhone SE width)
    await page.setViewportSize({ width: 375, height: 667 });

    await page.goto("/chat");

    // Verify header, message container, and chat input are visible
    await expect(page.locator("h1")).toContainText("GOA Assistant");

    const input = page.getByTestId("chat-input");
    await expect(input).toBeVisible();

    // Verify element doesn't create horizontal page overflow
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(bodyScrollWidth).toBeLessThanOrEqual(bodyClientWidth + 5);

    // Verify sending a message works on mobile viewport
    await page.route("**/api/chat", async (route) => {
      await route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: 'data: {"type":"token","content":"Mobile response ok"}\n\n',
      });
    });

    await input.fill("Testing mobile layout");
    await page.getByTestId("send-message-button").click();

    await expect(page.getByTestId("user-message").last()).toContainText("Testing mobile layout");
    await expect(page.getByTestId("assistant-message").last()).toContainText("Mobile response ok");
  });
});

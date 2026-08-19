import { test, expect, type Page } from "./fixtures/auth";

/**
 * Live, end-to-end Academic Writing flow against the real stack.
 *
 * Unlike writing-exam.spec.ts — which stubs every Gateway response so the wiring
 * can be proven deterministically — this spec talks to a running docker-compose:
 * Gateway (:8080) → exam service → writing service → LLM, with LocalStack S3
 * holding the Task 1 stimulus chart. It exists to catch the things a mock never
 * can: that the exam service actually mints a browser-reachable pre-signed URL,
 * that the chart bytes resolve (not a 404 / broken image), and that a real LLM
 * evaluation renders as a band, four criterion scores and highlighted issues.
 *
 * It is skipped unless E2E_LIVE_WRITING is set, so the normal suite never
 * depends on a live backend. See the run instructions at the bottom of the file.
 *
 * Prerequisites when E2E_LIVE_WRITING=1:
 *   - `make up` (or docker compose up) with gateway, exam, writing, localstack
 *     and the LLM reachable, AND the Task 1 image-delivery backend deployed
 *     (services/exam QuestionResponse.image_url is populated at session start).
 *   - The stimulus chart uploaded to S3 (services/exam/scripts/parse_books.py).
 *   - A PAID-tier E2E user (the /api/exam group is behind the GOA-059 paid gate;
 *     a free user gets 403 subscription_required on create). Credentials via
 *     E2E_LIVE_EMAIL / E2E_LIVE_PASSWORD.
 */

const live = !!process.env.E2E_LIVE_WRITING;

// The Gateway origin the app talks to (BUG-046). Login and the session-seeding
// API calls go here directly; the browser reuses the same cookie jar (cookies
// are host-scoped to `localhost`, so they serve both :3000 and :8080).
const GATEWAY = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";
const EXAM_API = `${GATEWAY}/api/exam`;

const EMAIL = process.env.E2E_LIVE_EMAIL ?? "";
const PASSWORD = process.env.E2E_LIVE_PASSWORD ?? "";

// A session known to carry the Academic Task 1 chart. Optional: when set, the
// test targets it directly and skips the create-until-chart loop below. Seed one
// per fady-context/WRITING-EXAM-FLOW-HANDOFF.md and export its id here for a
// fully deterministic run.
const KNOWN_SESSION_ID = process.env.E2E_LIVE_SESSION_ID ?? "";

// How many fresh sessions to create looking for one whose randomly-selected
// question carries a chart. Question selection is random and only a subset of
// Academic Writing questions are visual, so this is best-effort: if none turns
// up, the test skips with guidance rather than failing on seed-data odds.
const MAX_SESSION_ATTEMPTS = 15;

// Real sample responses. Task 1 deliberately contains a few plain grammar slips
// ("The chart show", "have rised", "more higher") so the evaluation reliably
// surfaces at least one inline issue to highlight — the alternative, a flawless
// essay, would make the highlight assertion depend on the model inventing one.
const TASK1_ESSAY = [
  "The chart show the amount of money that households in four different",
  "countries spent on food, housing and leisure over a ten year period.",
  "Overall, spending on housing was the largest category in every country,",
  "while leisure spending have rised steadily across the whole period.",
  "In the first year, households spent around thirty percent of their income",
  "on housing, and this figure became more higher by the final year, reaching",
  "almost forty percent. Food spending, by contrast, fell gradually from",
  "twenty five percent to under twenty percent, which suggests that the cost",
  "of housing squeezed the other categories. Leisure remained the smallest",
  "category throughout, but it was the only one to grow in relative terms,",
  "climbing from roughly ten percent to fifteen percent of total household",
  "spending. In summary, the data shows a clear shift towards housing costs",
  "at the expense of food, with leisure making modest but consistent gains",
  "over the decade in all of the countries that were surveyed in the study.",
].join(" ");

const TASK2_ESSAY = [
  "Some people argue that modern technology has made everyday life more",
  "complicated rather than simpler, and there is certainly evidence on both",
  "sides of this debate. In this essay I will discuss both views before",
  "explaining why I believe the benefits ultimately outweigh the drawbacks.",
  "On the one hand, it is true that technology can add complexity. Many",
  "people feel obliged to remain constantly available through email and",
  "messaging, which blurs the line between work and rest and can raise stress",
  "levels. Devices also break, require updates and demand new skills, so a",
  "task that was once simple, such as paying a bill, may now involve",
  "passwords, applications and verification codes. For less confident users,",
  "particularly the elderly, this can be genuinely bewildering. On the other",
  "hand, the same tools remove far more friction than they create. A journey",
  "that once needed printed maps and timetables is now handled by a single",
  "application, and medical records, banking and education are all more",
  "accessible than ever before. What feels complicated is often simply",
  "unfamiliar, and the underlying task has in fact become easier and faster.",
  "In conclusion, although technology introduces new demands, it resolves",
  "many more of the problems that used to make daily life difficult. On",
  "balance, therefore, I believe it has simplified life rather than",
  "complicated it, provided that people are given the support they need to",
  "adapt to the tools that are now an unavoidable part of the modern world.",
].join(" ");

const CRITERIA = ["task_response", "cohesion", "vocabulary", "grammar"] as const;

/** Log in against the live Gateway; the browser context inherits the cookies. */
async function signIn(page: Page) {
  const response = await page.request.post(`${GATEWAY}/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(
    response.ok(),
    `Login failed (${response.status()}). Set E2E_LIVE_EMAIL / E2E_LIVE_PASSWORD to a valid paid-tier user.`,
  ).toBeTruthy();

  // Confirm the guard cookie actually landed — Playwright stores HttpOnly
  // cookies in the context jar even though JS can't read them.
  const cookies = await page.context().cookies();
  expect(
    cookies.some((c) => c.name === "access_token"),
    "Login succeeded but no access_token cookie was set; the middleware guard will bounce /exam.",
  ).toBeTruthy();
}

/**
 * Resolve a session whose Task 1 carries a pre-signed chart.
 *
 * Prefers E2E_LIVE_SESSION_ID when provided (deterministic). Otherwise creates
 * Academic Writing sessions until one comes back with a non-null image_url, or
 * gives up after MAX_SESSION_ATTEMPTS. Returns the id plus the chart URL the
 * backend reported, so the UI assertion can be checked against the source.
 */
async function findChartSession(
  page: Page,
): Promise<{ sessionId: string; imageUrl: string } | null> {
  if (KNOWN_SESSION_ID) {
    const r = await page.request.get(`${EXAM_API}/sessions/${KNOWN_SESSION_ID}`);
    expect(r.ok(), `E2E_LIVE_SESSION_ID ${KNOWN_SESSION_ID} not fetchable (${r.status()}).`).toBeTruthy();
    const body = await r.json();
    const imageUrl = body?.questions?.[0]?.image_url ?? null;
    expect(
      imageUrl,
      `E2E_LIVE_SESSION_ID ${KNOWN_SESSION_ID} has no Task 1 image_url; point it at a chart-bearing session.`,
    ).toBeTruthy();
    return { sessionId: KNOWN_SESSION_ID, imageUrl };
  }

  for (let attempt = 1; attempt <= MAX_SESSION_ATTEMPTS; attempt++) {
    const r = await page.request.post(`${EXAM_API}/sessions`, {
      data: { exam_type: "academic", skill_area: "writing" },
    });
    if (r.status() === 403) {
      throw new Error(
        "createSession returned 403 subscription_required — the E2E user must be on a paid tier.",
      );
    }
    expect(r.ok(), `createSession failed on attempt ${attempt} (${r.status()}).`).toBeTruthy();

    const body = await r.json();
    const sessionId: string = body.session_id;
    const imageUrl: string | null = body?.first_question_set?.image_url ?? null;
    if (imageUrl) {
      // eslint-disable-next-line no-console
      console.log(`Found chart-bearing session on attempt ${attempt}: ${sessionId}`);
      return { sessionId, imageUrl };
    }
  }
  return null;
}

/** Submit one task through the UI and wait for its evaluated result card. */
async function submitTask(page: Page, taskNumber: 1 | 2, essay: string) {
  await page.getByTestId(`writing-task-tab-${taskNumber}`).click();
  await page.getByTestId(`task-${taskNumber}-textarea`).fill(essay);
  await page.getByTestId(`task-${taskNumber}-submit`).click();
}

test.describe("Academic Writing — live E2E", () => {
  // The point of this spec is the live path, so opt out of the fixture's
  // placeholder cookie and authenticate for real instead.
  test.use({ authenticated: false });

  test.skip(!live, "Set E2E_LIVE_WRITING=1 with the full stack (gateway+exam+writing+LLM+localstack) running.");
  test.skip(live && (!EMAIL || !PASSWORD), "Set E2E_LIVE_EMAIL and E2E_LIVE_PASSWORD for the live writing E2E.");

  // A real LLM round-trip on two essays is slow; give the whole journey room.
  test.setTimeout(5 * 60 * 1000);

  test("chart delivers, essays submit, and the evaluation renders", async ({
    page,
  }) => {
    // 1) Start session — sign in, then obtain a chart-bearing session.
    await signIn(page);

    const target = await findChartSession(page);
    test.skip(
      target === null,
      `No chart-bearing Academic Writing session found in ${MAX_SESSION_ATTEMPTS} tries. ` +
        "Seed one (see fady-context/WRITING-EXAM-FLOW-HANDOFF.md) and set E2E_LIVE_SESSION_ID.",
    );
    const { sessionId, imageUrl } = target!;

    await page.goto(`/exam/shell?session=${sessionId}`);
    await expect(page.getByTestId("writing-task-tab-1")).toBeVisible();

    // 2) Verify chart delivery — the <img> exists, its src is the pre-signed S3
    //    URL the backend reported, and the bytes actually resolve.
    const image = page.getByTestId("stimulus-image-1");
    await expect(image).toBeVisible();

    const src = await image.getAttribute("src");
    expect(src, "Task 1 image has no src").toBeTruthy();
    // A SigV4 pre-signed URL carries the signature in its query string; a raw
    // internal key or an un-signed link would not, and a browser could not load
    // it. This is the assertion a mock cannot make honestly.
    expect(src!).toMatch(/[?&]X-Amz-(Signature|Credential)=/);
    expect(src!).toBe(imageUrl);

    // It decoded to real pixels — i.e. the URL resolved, not a 404/broken image.
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth), {
        timeout: 15_000,
      })
      .toBeGreaterThan(0);

    // And it is independently reachable over HTTP (the strongest not-404 check).
    const head = await page.request.get(src!);
    expect(head.ok(), `Stimulus URL did not resolve: ${head.status()}`).toBeTruthy();

    // Zoom control opens the enlarged view and Escape dismisses it.
    await page.getByTestId("stimulus-zoom-button-1").click();
    await expect(page.getByTestId("stimulus-zoom-modal-1")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("stimulus-zoom-modal-1")).toHaveCount(0);

    // 3 & 4) Input real data and submit both tasks.
    await submitTask(page, 1, TASK1_ESSAY);
    // Task 1 evaluates in place while Task 2 stays editable — a collapsed card
    // appears and the full-screen "Analyzing..." overlay must NOT (still sitting).
    await expect(page.getByTestId("task-1-result-card")).toBeVisible({
      timeout: 3 * 60 * 1000,
    });
    await expect(page.getByText("Analyzing performance...")).toHaveCount(0);

    await submitTask(page, 2, TASK2_ESSAY);

    // 5) Verify the evaluation UI on the results page.
    await expect(page).toHaveURL(/\/exam\/results\?session=.*skill=Writing/, {
      timeout: 3 * 60 * 1000,
    });

    // Overall band: a real IELTS band (0–9, half steps), not a specific value —
    // the LLM output is not deterministic.
    const overall = page.getByTestId("writing-overall-band");
    await expect(overall).toBeVisible();
    const overallText = (await overall.textContent())?.trim() ?? "";
    expect(overallText).toMatch(/^\d(\.\d)?$/);
    const overallBand = Number(overallText);
    expect(overallBand).toBeGreaterThanOrEqual(0);
    expect(overallBand).toBeLessThanOrEqual(9);

    // The weighted-formula line renders (exact numbers are band-dependent).
    await expect(page.getByTestId("writing-weighting-formula")).toContainText(
      /Task 1:.*Task 2:.*Band/,
    );

    // Both task cards, each with a band and all four criterion scores.
    for (const taskNumber of [1, 2] as const) {
      const card = page.getByTestId(`task-${taskNumber}-result-card`);
      await expect(card).toBeVisible();
      await expect(page.getByTestId(`task-${taskNumber}-band`)).toHaveText(
        /^\d(\.\d)?$/,
      );
      for (const c of CRITERIA) {
        await expect(
          page.getByTestId(`task-${taskNumber}-criterion-${c}`),
        ).toBeVisible();
      }
    }

    // Highlighted issues: expand Task 1 and assert the annotated essay renders
    // with at least one criterion-coloured span. The Task 1 essay carries plain
    // grammar slips, so a working evaluation reliably marks one; if a model ever
    // returns a spotless read this is the assertion to relax to >= 0.
    await page.getByTestId("task-1-result-toggle").click();
    await expect(page.getByTestId("task-1-expanded")).toBeVisible();

    const highlights = page.getByTestId("highlight-span");
    await expect
      .poll(() => highlights.count(), { timeout: 10_000 })
      .toBeGreaterThan(0);
    await expect(
      page.locator("[data-testid=highlight-span][data-criterion]").first(),
    ).toBeVisible();
  });
});

/*
 * How to run it and watch the browser drive the flow
 * ---------------------------------------------------
 * 1. Bring the backend up (from repo root):
 *      make up        # gateway + exam + writing + localstack + LLM
 *    Make sure the Task 1 image-delivery backend is deployed and the chart is in
 *    S3 (services/exam/scripts/parse_books.py uploads it).
 *
 * 2. From services/frontend, run the spec headed against a dev server so you can
 *    watch it, with a real paid-tier user:
 *
 *      E2E_LIVE_WRITING=1 \
 *      E2E_DEV_SERVER=true \
 *      E2E_LIVE_EMAIL=you@example.com \
 *      E2E_LIVE_PASSWORD=... \
 *      npx playwright test writing-exam-live --headed --workers=1 --project=chromium
 *
 *    Add `E2E_LIVE_SESSION_ID=<uuid>` (a pre-seeded chart-bearing session) for a
 *    deterministic run that skips the create-until-chart search. Use
 *    `--debug` to step through, or `--ui` for Playwright's time-travel UI.
 */

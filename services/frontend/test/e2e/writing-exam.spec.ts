import { test, expect, Page, Route } from "./fixtures/auth";

// These tests stub the Gateway's REST responses at the network layer, the
// established pattern in this repo (see test/e2e/reading-exam.spec.ts), so the
// full Writing exam flow — task 1 submit -> compact card -> task 2 submit ->
// weighted combined result — can be verified against deterministic data with
// no Gateway, exam service, writing service or LLM in the loop.
//
// Every exam call goes through the Gateway on localhost:8080 (BUG-046), a
// different origin than the app on localhost:3000, and carries JSON plus
// credentials: "include". That makes the browser issue a CORS preflight
// (OPTIONS) before the real GET/PUT, and credentials: "include" additionally
// forbids a wildcard Access-Control-Allow-Origin — both are handled below.
const GATEWAY_API_BASE = "http://localhost:8080/api/exam";
const SESSION_ID = "33333333-3333-3333-3333-333333333333";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Credentials": "true",
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: corsHeaders(),
    body: JSON.stringify(body),
  });
}

async function withPreflight(
  route: Route,
  handle: (route: Route) => Promise<void>,
) {
  if (route.request().method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders() });
    return;
  }
  await handle(route);
}

function criterion(
  name: string,
  band: number,
  issue?: {
    text: string;
    issue_type: string;
    suggestion: string;
    start: number;
  },
) {
  return {
    criterion: name,
    band_score: band,
    feedback: `${name} feedback text.`,
    improvement_tip: `${name} tip.`,
    word_count: 160,
    inline_issues: issue
      ? [
          {
            text: issue.text,
            issue_type: issue.issue_type,
            suggestion: issue.suggestion,
            start_char: issue.start,
            end_char: issue.start + issue.text.length,
          },
        ]
      : [],
  };
}

// Mirrors services/writing/app/schemas.py exactly: inline_issues, issue_type,
// start_char/end_char. Using the producer's real field names here is the point
// — the previous mismatch between the services was invisible to tests that
// invented their own shape.
// Offsets must not overlap: EssayHighlighter resolves overlapping ranges
// first-match-wins and silently drops the loser, so two issues both starting at
// char 0 would render only one mark. Real offsets come from a substring search
// against the essay, so they never collide this way.
function evaluations(band: number) {
  return [
    criterion("task_response", band, {
      text: "word0",
      issue_type: "Overused opener",
      suggestion: "To begin with",
      start: 0,
    }),
    criterion("cohesion", band),
    criterion("vocabulary", band, {
      text: "word1",
      issue_type: "Imprecise word choice",
      suggestion: "substantial",
      start: 6,
    }),
    criterion("grammar", band),
  ];
}

interface SessionOptions {
  // Set-level pre-signed chart URL, mirroring the exam service's
  // QuestionResponse.image_url. Only Academic Task 1 renders it; null for
  // General Training and any set whose stimulus was unavailable.
  imageUrl?: string | null;
  // A per-task image field of the legacy/stray shape. The chart is delivered at
  // the question-set level, never per entry, so this must be ignored entirely.
  withStrayImageField?: boolean;
}

function sessionResponse(
  examType: "academic" | "general",
  options: SessionOptions = {},
) {
  const task1: Record<string, unknown> = {
    number: 1,
    prompt:
      examType === "academic"
        ? "The chart below shows household spending. Summarise the information."
        : "You recently had a problem with your apartment. Write a letter to your landlord.",
    instructions:
      examType === "academic"
        ? "Write at least 150 words."
        : "Write a letter of at least 150 words.",
  };

  // Simulates a backend that carries a legacy per-task image key. The chart is
  // delivered at the question-set level (image_url); a per-entry field is not a
  // stimulus source and the UI must ignore it entirely.
  if (options.withStrayImageField) {
    task1.stimulus_image_url = "https://s3.example/stray.png?sig=xyz";
    task1.image_s3_key = "writing-stimuli/chart.png";
  }

  return {
    id: SESSION_ID,
    user_id: "00000000-0000-0000-0000-000000000001",
    exam_type: examType,
    skill_area: "writing",
    status: "in_progress",
    started_at: new Date().toISOString(),
    submitted_at: null,
    time_limit_seconds: 3600,
    remaining_time_seconds: 3600,
    questions: [
      {
        id: "question-set-1",
        book_ref: "test-book",
        test_number: 1,
        exam_type: examType,
        skill_area: "writing",
        passage_text: null,
        audio_s3_key: null,
        // The Academic Task 1 chart is a pre-signed URL on the question SET,
        // exactly as services/exam/app/schemas/question.py (QuestionResponse)
        // exposes it. null for General Training and any set with no stimulus.
        image_url: options.imageUrl ?? null,
        questions: [
          task1,
          {
            number: 2,
            prompt: "Some people believe technology complicates life. Discuss.",
            instructions: "Write at least 250 words.",
          },
        ],
      },
    ],
  };
}

const TASK1_BAND = 6.5;
const TASK2_BAND = 7.0;
// The exam service's rule: round((6.5 + 2*7.0) / 3 * 2) / 2 = 7.0
const OVERALL_BAND = 7.0;

// A stand-in for the exam service's pre-signed stimulus URL. The shape mirrors a
// real LocalStack/S3 SigV4 link (host + query signature) so the assertions read
// like the live ones; the route below actually serves bytes for it, so the
// rendered <img> genuinely loads rather than 404-ing.
const STIMULUS_IMAGE_URL =
  "http://localhost:4566/exam-writing-stimuli/charts/test-book-test-1-task1.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=deadbeefcafef00d";

// Smallest valid PNG (1×1, transparent). Enough for the browser to decode the
// image and report naturalWidth > 0 — i.e. "the src resolved, not a broken
// image", the mocked-suite equivalent of the live not-404 check.
const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/**
 * Installs the full mock backend. `onSubmit` records each task submitted so a
 * test can assert what the UI actually sent.
 */
async function mockExamApi(
  page: Page,
  examType: "academic" | "general",
  submitted: number[],
  options: SessionOptions = {},
) {
  // Serve real bytes for the pre-signed stimulus URL so the rendered <img>
  // actually decodes. Registered before the session route (Playwright matches
  // most-recently-added first, but these patterns are disjoint) and only hit
  // when a test supplies an imageUrl pointing here.
  await page.route(STIMULUS_IMAGE_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/png",
      headers: corsHeaders(),
      body: PNG_1X1,
    }),
  );

  await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}`, (route) =>
    withPreflight(route, (r) =>
      fulfillJson(r, sessionResponse(examType, options)),
    ),
  );

  await page.route(
    `${GATEWAY_API_BASE}/sessions/${SESSION_ID}/heartbeat`,
    (route) => withPreflight(route, (r) => fulfillJson(r, { ok: true })),
  );

  await page.route(
    `${GATEWAY_API_BASE}/sessions/${SESSION_ID}/submit`,
    (route) =>
      withPreflight(route, async (r) => {
        const body = r.request().postDataJSON() as {
          task_number: number;
          essay_text: string;
        };
        submitted.push(body.task_number);

        const isTask1 = body.task_number === 1;
        const band = isTask1 ? TASK1_BAND : TASK2_BAND;
        const wordCount = body.essay_text.trim().split(/\s+/).length;

        await fulfillJson(r, {
          session_id: SESSION_ID,
          task_number: body.task_number,
          status: submitted.length >= 2 ? "submitted" : "task_submitted",
          overall_band: band,
          word_count: wordCount,
          penalty_flag: wordCount < (isTask1 ? 150 : 250),
          evaluations: evaluations(band),
        });
      }),
  );

  await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}/result`, (route) =>
    withPreflight(route, (r) =>
      fulfillJson(r, {
        session_id: SESSION_ID,
        user_id: "00000000-0000-0000-0000-000000000001",
        skill_area: "writing",
        overall_band: OVERALL_BAND,
        tasks: {
          "1": {
            response_text: "Task one response text.",
            word_count: 155,
            penalty_flag: false,
            evaluation: {
              evaluations: evaluations(TASK1_BAND),
              overall_band: TASK1_BAND,
            },
          },
          "2": {
            response_text: "Task two response text.",
            word_count: 265,
            penalty_flag: false,
            evaluation: {
              evaluations: evaluations(TASK2_BAND),
              overall_band: TASK2_BAND,
            },
          },
        },
      }),
    ),
  );
}

function words(count: number): string {
  return Array.from({ length: count }, (_, i) => `word${i}`).join(" ");
}

async function openExam(page: Page) {
  await page.goto(`/exam/shell?session=${SESSION_ID}`);
  await expect(page.getByTestId("writing-task-tab-1")).toBeVisible();
}

test.describe("Writing exam UI", () => {
  // The Academic Task 1 stimulus chart is delivered as a pre-signed URL on the
  // question set (QuestionResponse.image_url). It renders only for Academic
  // Task 1 and only when the payload carried one; General Training, Task 2 and
  // any set with a null image_url stay prompt-only.
  test("Academic Task 1 renders the pre-signed chart and it actually loads", async ({
    page,
  }) => {
    await mockExamApi(page, "academic", [], { imageUrl: STIMULUS_IMAGE_URL });
    await openExam(page);

    await expect(page.getByTestId("stimulus-prompt-1")).toContainText(
      "The chart below shows household spending",
    );

    const image = page.getByTestId("stimulus-image-1");
    await expect(image).toBeVisible();
    // The src is the pre-signed URL verbatim (next/image `unoptimized` — it must
    // not be re-keyed through the optimizer, which would drop the signature).
    await expect(image).toHaveAttribute("src", STIMULUS_IMAGE_URL);
    // ...and it decoded: naturalWidth > 0 means the URL resolved to real bytes,
    // not a broken image. This is the mocked-suite mirror of the live not-404
    // assertion.
    await expect
      .poll(() =>
        image.evaluate((img: HTMLImageElement) => img.naturalWidth),
      )
      .toBeGreaterThan(0);
  });

  test("Academic Task 1 zoom opens a modal and Escape closes it", async ({
    page,
  }) => {
    await mockExamApi(page, "academic", [], { imageUrl: STIMULUS_IMAGE_URL });
    await openExam(page);

    const modal = page.getByTestId("stimulus-zoom-modal-1");
    await expect(modal).toHaveCount(0);

    await page.getByTestId("stimulus-zoom-button-1").click();
    await expect(modal).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
  });

  test("Academic Task 1 with no chart stays prompt-only", async ({ page }) => {
    // A session whose stimulus was unavailable degrades to image_url: null. The
    // task must still render, prompt-only, with no image or zoom control.
    await mockExamApi(page, "academic", [], { imageUrl: null });
    await openExam(page);

    await expect(page.getByTestId("stimulus-prompt-1")).toContainText(
      "The chart below shows household spending",
    );
    await expect(page.getByTestId("stimulus-image-1")).toHaveCount(0);
    await expect(page.getByTestId("stimulus-zoom-button-1")).toHaveCount(0);
    await expect(page.getByTestId("task-1-textarea")).toBeEditable();
  });

  test("Academic Task 1 ignores a stray per-task image field", async ({
    page,
  }) => {
    // The chart is delivered at the question-set level, never per entry. A
    // legacy per-task image field must be ignored, never rendered and never
    // fatal — so with no set-level image_url the task stays prompt-only.
    await mockExamApi(page, "academic", [], { withStrayImageField: true });
    await openExam(page);

    await expect(page.getByTestId("stimulus-prompt-1")).toBeVisible();
    await expect(page.getByTestId("stimulus-image-1")).toHaveCount(0);
    await expect(page.getByTestId("task-1-textarea")).toBeEditable();
  });

  test("General Training Task 1 shows scenario text and no image", async ({
    page,
  }) => {
    // General Training Task 1 is a letter scenario — prose by nature, and the
    // exam service never mints an image_url for it even though the field exists.
    await mockExamApi(page, "general", [], { imageUrl: STIMULUS_IMAGE_URL });
    await openExam(page);

    await expect(page.getByTestId("stimulus-scenario-text-1")).toContainText(
      "Write a letter to your landlord",
    );
    await expect(page.getByTestId("stimulus-image-1")).toHaveCount(0);
    await expect(page.getByTestId("stimulus-zoom-button-1")).toHaveCount(0);
  });

  test("word counter is orange at 148 words and green at 150", async ({
    page,
  }) => {
    await mockExamApi(page, "academic", []);
    await openExam(page);

    const textarea = page.getByTestId("task-1-textarea");
    const counter = page.getByTestId("task-1-word-counter");

    // The computed values below are the app's --warning-fg and --success-fg
    // design tokens (globals.css) as this browser resolves them. Asserting
    // the rendered colour, not just the class, is the point — "warning below
    // target, success at target" is the acceptance criterion, and a class
    // name alone would not catch a broken palette.
    const ORANGE = "rgb(133, 83, 7)"; // --warning-fg: #855307
    const GREEN = "rgb(23, 97, 47)"; // --success-fg: #17612f

    await textarea.fill(words(148));
    await expect(counter).toHaveText("148 / 150 words");
    await expect(counter).toHaveAttribute("data-state", "below");
    await expect(counter).toHaveCSS("color", ORANGE);

    await textarea.fill(words(150));
    await expect(counter).toHaveText("150 / 150 words");
    await expect(counter).toHaveAttribute("data-state", "met");
    await expect(counter).toHaveCSS("color", GREEN);
  });

  test("under-minimum warning appears below target and clears at target", async ({
    page,
  }) => {
    await mockExamApi(page, "academic", []);
    await openExam(page);

    const textarea = page.getByTestId("task-1-textarea");
    const warning = page.getByTestId("task-1-under-minimum-warning");

    await textarea.fill(words(20));
    await expect(warning).toBeVisible();
    await expect(warning).toHaveText(
      "Responses under 150 words are penalised for Task Achievement (criterion 1).",
    );

    await textarea.fill(words(150));
    await expect(warning).toHaveCount(0);
  });

  test("shows the recommended time split per task", async ({ page }) => {
    await mockExamApi(page, "academic", []);
    await openExam(page);

    await expect(page.getByTestId("task-1-suggested-time")).toHaveText(
      "Suggested: 20 min for Task 1",
    );

    await page.getByTestId("writing-task-tab-2").click();
    await expect(page.getByTestId("task-2-suggested-time")).toHaveText(
      "Suggested: 40 min for Task 2",
    );
  });

  test("Task 2 keeps its draft across tab switches", async ({ page }) => {
    await mockExamApi(page, "academic", []);
    await openExam(page);

    await page.getByTestId("task-1-textarea").fill("Task one draft.");
    await page.getByTestId("writing-task-tab-2").click();
    await page.getByTestId("task-2-textarea").fill("Task two draft.");

    await page.getByTestId("writing-task-tab-1").click();
    await expect(page.getByTestId("task-1-textarea")).toHaveValue(
      "Task one draft.",
    );

    await page.getByTestId("writing-task-tab-2").click();
    await expect(page.getByTestId("task-2-textarea")).toHaveValue(
      "Task two draft.",
    );
  });

  test("Task 1 submit yields a collapsed card while Task 2 stays editable", async ({
    page,
  }) => {
    const submitted: number[] = [];
    await mockExamApi(page, "academic", submitted);
    await openExam(page);

    await page.getByTestId("task-1-textarea").fill(words(160));
    await page.getByTestId("task-1-submit").click();

    // The shell's full-screen "Analysing performance..." overlay must never
    // appear for a single task — the candidate is still sitting the exam.
    await expect(page.getByText("Analyzing performance...")).toHaveCount(0);

    await page.getByTestId("writing-task-tab-1").click();
    const card = page.getByTestId("task-1-result-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-expanded", "false");
    await expect(page.getByTestId("task-1-band")).toHaveText("6.5");

    // Top issue per criterion, colour-coded, in the collapsed card.
    for (const name of ["task_response", "cohesion", "vocabulary", "grammar"]) {
      await expect(
        page.getByTestId(`task-1-criterion-${name}`),
      ).toBeVisible();
    }
    await expect(
      page.getByTestId("task-1-criterion-task_response"),
    ).toContainText("Overused opener");

    // Expandable, revealing the reused EssayHighlighter mark-up.
    await expect(page.getByTestId("task-1-expanded")).toHaveCount(0);
    await page.getByTestId("task-1-result-toggle").click();
    await expect(page.getByTestId("task-1-expanded")).toBeVisible();
    await expect(
      page.locator('[data-criterion="vocabulary"]').first(),
    ).toBeVisible();

    // Task 2 remains fully editable throughout.
    await page.getByTestId("writing-task-tab-2").click();
    const task2 = page.getByTestId("task-2-textarea");
    await expect(task2).toBeEnabled();
    await task2.fill("Task 2 is still editable while task 1 was evaluated.");
    await expect(task2).toHaveValue(
      "Task 2 is still editable while task 1 was evaluated.",
    );

    expect(submitted).toEqual([1]);
  });

  test("both tasks evaluated then the weighted band is displayed", async ({
    page,
  }) => {
    const submitted: number[] = [];
    await mockExamApi(page, "academic", submitted);
    await openExam(page);

    await page.getByTestId("task-1-textarea").fill(words(160));
    await page.getByTestId("task-1-submit").click();
    await expect(page.getByTestId("task-1-result-card")).toBeHidden();

    // Submitting task 1 moves focus to the task still to be written.
    const task2 = page.getByTestId("task-2-textarea");
    await expect(task2).toBeVisible();
    await task2.fill(words(270));
    await page.getByTestId("task-2-submit").click();

    await expect(page).toHaveURL(/\/exam\/results\?session=.*skill=Writing/);

    await expect(page.getByTestId("writing-overall-band")).toHaveText("7.0");
    await expect(page.getByTestId("writing-weighting-formula")).toHaveText(
      "(Task 1: 6.5 × 33%) + (Task 2: 7.0 × 67%) = 6.8 → Band 7.0",
    );

    // Both tasks side by side on the results page.
    await expect(page.getByTestId("task-1-result-card")).toBeVisible();
    await expect(page.getByTestId("task-2-result-card")).toBeVisible();
    await expect(page.getByTestId("task-1-band")).toHaveText("6.5");
    await expect(page.getByTestId("task-2-band")).toHaveText("7.0");

    expect(submitted).toEqual([1, 2]);
  });

  test("a failed task submit leaves the exam usable", async ({ page }) => {
    await mockExamApi(page, "academic", []);
    // Override the submit route with a failure.
    await page.route(
      `${GATEWAY_API_BASE}/sessions/${SESSION_ID}/submit`,
      (route) =>
        withPreflight(route, (r) =>
          fulfillJson(r, { detail: "Writing service unavailable" }, 502),
        ),
    );

    await openExam(page);
    await page.getByTestId("task-1-textarea").fill(words(160));
    await page.getByTestId("task-1-submit").click();

    await expect(page.getByTestId("task-1-error")).toBeVisible();
    // The draft survives and the task can be retried.
    await expect(page.getByTestId("task-1-textarea")).toHaveValue(words(160));
    await expect(page.getByTestId("task-1-submit")).toBeEnabled();
  });
});

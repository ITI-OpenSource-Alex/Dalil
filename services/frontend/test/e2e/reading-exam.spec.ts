import { test, expect, Page, Route } from "./fixtures/auth";
import {
  READING_PASSAGES,
  READING_QUESTIONS,
  buildReadingSubmitResponse,
} from "./fixtures/reading-questions";

// These tests stub the Gateway's REST responses at the network layer (see
// test/e2e/speaking-history-mocked.spec.ts for the established pattern in
// this repo), so the full Reading exam-taking -> submit -> results flow can
// be verified against known, deterministic data without requiring the
// Gateway, exam service, or a real logged-in JWT session. Every Reading
// call now goes through the Gateway (localhost:8080/api/exam/*), not the
// exam service directly (BUG-046 — see lib/exam-api.ts / lib/reading-api.ts)
// — a different origin than the frontend (localhost:3000), and the request
// carries JSON + credentials: "include", which makes the browser issue a
// CORS preflight (OPTIONS) before the real GET/PUT — both must be handled.
// credentials: "include" additionally requires an explicit (non-wildcard)
// Access-Control-Allow-Origin plus Access-Control-Allow-Credentials.
const GATEWAY_API_BASE = "http://localhost:8080/api/exam";
const SESSION_ID = "22222222-2222-2222-2222-222222222222";

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "http://localhost:3000",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
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

const SESSION_RESPONSE = {
  id: SESSION_ID,
  user_id: "00000000-0000-0000-0000-000000000001",
  exam_type: "academic",
  skill_area: "reading",
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
      exam_type: "academic",
      skill_area: "reading",
      passage_text: READING_PASSAGES.join("---"),
      audio_s3_key: null,
      questions: READING_QUESTIONS,
    },
  ],
};

/** Mocks the Gateway's GET /api/exam/sessions/:id and
 * PUT /api/exam/reading/:id/submit, and exposes a getter for whatever
 * answers payload was actually sent to submit — used to assert highlights
 * never leak into it. */
async function mockReadingBackend(page: Page) {
  let submittedAnswers: Record<string, string> | null = null;

  await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}`, (route) =>
    withPreflight(route, (r) => fulfillJson(r, SESSION_RESPONSE)),
  );

  await page.route(
    `${GATEWAY_API_BASE}/reading/${SESSION_ID}/submit`,
    (route) =>
      withPreflight(route, (r) => {
        const body = r.request().postDataJSON() as {
          answers: Record<string, string>;
        };
        submittedAnswers = body.answers;
        return fulfillJson(r, buildReadingSubmitResponse(body.answers));
      }),
  );

  return {
    getSubmittedAnswers: () => submittedAnswers,
  };
}

async function gotoReadingExam(page: Page) {
  await page.goto(`/exam/shell?session=${SESSION_ID}`);
  await expect(page.getByTestId("passage-panel")).toBeVisible();
}

test.describe("Dalil Reading exam (mocked backend)", () => {
  test("starts correctly with the passage and split, independently-scrollable layout", async ({
    page,
  }) => {
    await mockReadingBackend(page);
    await gotoReadingExam(page);

    await expect(page.getByText("Coral reefs are among")).toBeVisible();
    await expect(page.getByTestId("passage-panel")).toBeVisible();
    await expect(page.getByTestId("reading-split-handle")).toBeVisible();
    await expect(page.getByTestId("question-nav-sidebar")).toBeVisible();
    await expect(page.getByTestId("question-nav-legend")).toBeVisible();
    await expect(page.getByTestId("question-nav-legend")).toContainText(
      "Current",
    );
    await expect(page.getByTestId("question-nav-legend")).toContainText(
      "Answered",
    );
    await expect(page.getByTestId("question-nav-legend")).toContainText(
      "Unanswered",
    );
    await expect(page.getByTestId("question-1")).toBeVisible();
    await expect(page.getByTestId("section-tab-1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("passage highlighting is local: creating and removing a highlight never touches the submitted answers", async ({
    page,
  }) => {
    const backend = await mockReadingBackend(page);
    await gotoReadingExam(page);

    // Simulate selecting the first 11 characters ("Coral reefs") of the
    // first paragraph, then firing the mouseup PassagePanel listens for.
    await page.evaluate(() => {
      const paragraph = document.querySelector(
        '[data-testid="passage-paragraph"]',
      )!;
      const walker = document.createTreeWalker(
        paragraph,
        NodeFilter.SHOW_TEXT,
      );
      const textNode = walker.nextNode()!;
      const range = document.createRange();
      range.setStart(textNode, 0);
      range.setEnd(textNode, 11);
      const selection = window.getSelection()!;
      selection.removeAllRanges();
      selection.addRange(range);
    });
    await page
      .locator('[data-testid="passage-paragraph"]')
      .first()
      .dispatchEvent("mouseup");

    const highlight = page.getByTestId("passage-highlight");
    await expect(highlight).toHaveText("Coral reefs");

    // Click to remove it.
    await highlight.click();
    await expect(page.getByTestId("passage-highlight")).toHaveCount(0);

    // Answer one question and submit; the highlight interaction above must
    // have no trace in what gets sent.
    await page.locator('[data-testid="question-1"] input[value="B"]').check();
    await page.getByTestId("reading-submit-button").click();
    await page.getByTestId("confirm-submit-button").click();
    await expect(page).toHaveURL(/\/exam\/results\?session=.*skill=Reading/);

    const sent = backend.getSubmittedAnswers();
    expect(sent).toEqual({ "1": "B" });
  });

  test("all 5 question types are answerable, nav sidebar reflects answered state, and section switches preserve answers", async ({
    page,
  }) => {
    await mockReadingBackend(page);
    await gotoReadingExam(page);

    // Multiple Choice (section 1).
    await page.locator('[data-testid="question-1"] input[value="B"]').check();
    await expect(page.getByTestId("nav-circle-1")).toHaveAttribute(
      "data-answered",
      "true",
    );

    // True/False/Not Given (section 1).
    await page
      .locator('[data-testid="question-6"]')
      .getByRole("button", { name: "TRUE" })
      .click();
    await expect(page.getByTestId("nav-circle-6")).toHaveAttribute(
      "data-answered",
      "true",
    );

    // Switch to section 2 and confirm section-1 answers weren't touched by
    // switching away, then switch back and verify they're still there.
    await page.getByTestId("section-tab-2").click();
    await expect(page.getByTestId("question-14")).toBeVisible();

    // Matching (section 2, dropdown).
    await page
      .locator('[data-testid="question-14"] select')
      .selectOption("C");
    await expect(page.getByTestId("nav-circle-14")).toHaveAttribute(
      "data-answered",
      "true",
    );

    // Sentence Completion / Fill-in-Blank (section 2).
    await page
      .locator('[data-testid="question-20"] input[type="text"]')
      .fill("transportation");
    await expect(page.getByTestId("nav-circle-20")).toHaveAttribute(
      "data-answered",
      "true",
    );

    await page.getByTestId("section-tab-1").click();
    await expect(
      page.locator('[data-testid="question-1"] input[value="B"]'),
    ).toBeChecked();
    await expect(
      page
        .locator('[data-testid="question-6"]')
        .getByRole("button", { name: "TRUE" }),
    ).toHaveAttribute("aria-pressed", "true");

    // Short Answer (section 3), reached via nav-sidebar jump.
    await page.getByTestId("nav-circle-27").click();
    await expect(page.getByTestId("section-tab-3")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("question-27")).toBeVisible();
    await page
      .locator('[data-testid="question-27"] input[type="text"]')
      .fill("1969");
    await expect(page.getByTestId("nav-circle-27")).toHaveAttribute(
      "data-answered",
      "true",
    );

    // 5 answered across sections; footer shows dual progress for active
    // section (3) plus exam-wide total.
    await expect(page.getByTestId("reading-progress")).toHaveText(
      "Section 3: 1/14 · Exam: 5/40",
    );
  });

  test("submit confirmation modal shows the exact unanswered count and cancel does not submit", async ({
    page,
  }) => {
    await mockReadingBackend(page);
    await gotoReadingExam(page);

    await page.locator('[data-testid="question-1"] input[value="B"]').check();

    await page.getByTestId("reading-submit-button").click();
    await expect(page.getByTestId("unanswered-count-warning")).toContainText(
      "39",
    );

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page).toHaveURL(/\/exam\/shell/);
  });

  test("full flow: answer all 5 question types, submit, and verify the results page", async ({
    page,
  }) => {
    await mockReadingBackend(page);
    await gotoReadingExam(page);

    await page.locator('[data-testid="question-1"] input[value="B"]').check();
    await page
      .locator('[data-testid="question-6"]')
      .getByRole("button", { name: "TRUE" })
      .click();

    await page.getByTestId("section-tab-2").click();
    await page
      .locator('[data-testid="question-14"] select')
      .selectOption("C");
    await page
      .locator('[data-testid="question-20"] input[type="text"]')
      .fill("transportation");

    await page.getByTestId("section-tab-3").click();
    await page
      .locator('[data-testid="question-27"] input[type="text"]')
      .fill("1969");

    await page.getByTestId("reading-submit-button").click();
    await expect(page.getByTestId("unanswered-count-warning")).toContainText(
      "35",
    );
    await page.getByTestId("confirm-submit-button").click();

    await expect(page).toHaveURL(
      new RegExp(`/exam/results\\?session=${SESSION_ID}&skill=Reading`),
    );

    // Overall score.
    await expect(page.getByTestId("reading-results-view")).toBeVisible();
    await expect(page.getByTestId("reading-band-score")).toHaveText("6.5");

    // Per-question review: Q1 was answered "B" and is in the mocked
    // "correct" set; Q5 was never answered and is in the "incorrect" set.
    await expect(page.getByTestId("result-row-1")).toHaveAttribute(
      "data-correct",
      "true",
    );
    await expect(page.getByTestId("result-user-answer-1")).toHaveText("B");
    await expect(page.getByTestId("result-correct-answer-1")).toHaveText("B");
    await expect(page.getByTestId("result-passage-hint-1")).toContainText(
      "Passage 1",
    );

    await expect(page.getByTestId("result-row-5")).toHaveAttribute(
      "data-correct",
      "false",
    );
    await expect(page.getByTestId("result-user-answer-5")).toHaveText(
      "(no answer)",
    );

    // Question-type breakdown: Short Answer is the deliberate weakest type
    // (3/7) in the fixture's mocked response.
    await expect(page.getByTestId("question-type-breakdown")).toBeVisible();
    await expect(page.getByTestId("breakdown-short_answer")).toHaveAttribute(
      "data-weakest",
      "true",
    );
    await expect(page.getByTestId("breakdown-short_answer")).toContainText(
      "3/7",
    );
    await expect(page.getByTestId("breakdown-multiple_choice")).toContainText(
      "10/12",
    );

    // Section progress bars, read directly from the mocked response.
    await expect(page.getByTestId("section-breakdown-bars")).toBeVisible();
    await expect(page.getByTestId("section-bar-section_1")).toContainText(
      "10/13",
    );
    await expect(page.getByTestId("section-bar-section_2")).toContainText(
      "9/13",
    );
    await expect(page.getByTestId("section-bar-section_3")).toContainText(
      "9/14",
    );

    // "Practice Reading Again" navigation.
    await page.getByTestId("practice-reading-again-button").click();
    await expect(page).toHaveURL(/\/exam$/);
  });
});

/**
 * Regression guard: the floating assistant must never sit on top of the exam's
 * primary action.
 *
 * The Dalil chat pill is fixed to the bottom-right of the (app) layout, which
 * is where the Reading and Listening submit buttons live. When it mounted
 * inside the exam shell it intercepted their pointer events, and three Reading
 * specs plus two Listening specs timed out clicking a button Playwright
 * reported as visible, enabled, and covered. A candidate could not submit.
 *
 * Asserted two ways on purpose. Absence of the pill is the current fix;
 * clickability of the submit button is the actual requirement, and would still
 * hold if the widget were later reinstated somewhere harmless.
 */
test.describe("Reading exam — the assistant does not block submission", () => {
  test("no floating chat pill covers the submit button inside the exam shell", async ({
    page,
  }) => {
    await mockReadingBackend(page);
    await gotoReadingExam(page);

    await expect(
      page.getByTestId("dalil-chat-pill"),
      "the floating assistant is mounted inside the exam shell, where it " +
        "overlaps the submit control and compromises the simulation",
    ).toHaveCount(0);

    const submit = page.getByTestId("reading-submit-button");
    await expect(submit).toBeVisible();

    // The real requirement: whatever is on screen, the point the candidate
    // must click has to belong to the submit button.
    const box = await submit.boundingBox();
    expect(box).not.toBeNull();
    const topmost = await page.evaluate(
      ({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        return el?.closest("[data-testid]")?.getAttribute("data-testid") ?? el?.tagName ?? null;
      },
      { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 },
    );
    expect(
      topmost,
      `something else is on top of the submit button at its centre point: ${topmost}`,
    ).toBe("reading-submit-button");

    // Exercise the real pointer action too: the confirmation dialog is the
    // user-visible proof that Submit received the click.
    await submit.click();
    await expect(
      page.getByRole("dialog", { name: "Submit Reading exam?" }),
    ).toBeVisible();
  });
});

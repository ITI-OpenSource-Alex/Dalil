// ./fixtures/auth, not @playwright/test.
//
// middleware.ts guards /exam on the presence of an access_token cookie. Plain
// Playwright carries no session, so every test in this file was redirected to
// login and failed before reaching a single Listening assertion -- five
// "feature failures" that never touched the feature.
//
// The fixture re-exports Page and Route precisely so this is a one-line change.
import { test, expect, Page, Route } from "./fixtures/auth";

// Follows the same network-layer stubbing pattern as
// test/e2e/reading-mocked.spec.ts: every call goes through the Gateway
// (localhost:8080/api/exam/*), a different origin than the frontend
// (localhost:3000), so requests carry credentials: "include" and trigger a
// CORS preflight that must be handled alongside the real request.
const GATEWAY_API_BASE = "http://localhost:8080/api/exam";
const SESSION_ID = "33333333-3333-3333-3333-333333333333";

function createSilentWavBuffer(durationSeconds = 60): Buffer {
  const sampleRate = 8000;
  const numSamples = sampleRate * durationSeconds;
  const dataSize = numSamples;
  const buffer = Buffer.alloc(44 + dataSize);

  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(1, 22); // Mono
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate, 28); // Byte rate
  buffer.writeUInt16LE(1, 32); // Block align
  buffer.writeUInt16LE(8, 34); // 8-bit
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  buffer.fill(128, 44);

  return buffer;
}

const SILENT_WAV_BUFFER = createSilentWavBuffer(60);

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

// Four sections, kept small (3 questions each) so the test stays readable;
// the state machine and grading logic don't care about section size.
const SECTION_QUESTION_COUNT = 3;

function buildListeningQuestions() {
  const questions: Array<Record<string, unknown>> = [];
  let number = 1;
  for (let section = 1; section <= 4; section++) {
    for (let i = 0; i < SECTION_QUESTION_COUNT; i++) {
      questions.push({
        number,
        section_number: section,
        question_type: "sentence_completion",
        prompt: `Section ${section}, question ${number}`,
        options: null,
        correct_answer: `answer-${number}`,
      });
      number++;
    }
  }
  return questions;
}

const LISTENING_QUESTIONS = buildListeningQuestions();
const AUDIO_URLS = [1, 2, 3, 4].map(
  (section) => `${GATEWAY_API_BASE}/media/listening-section-${section}.wav`,
);

const SESSION_RESPONSE = {
  id: SESSION_ID,
  user_id: "00000000-0000-0000-0000-000000000001",
  exam_type: "academic",
  skill_area: "listening",
  status: "in_progress",
  started_at: new Date().toISOString(),
  submitted_at: null,
  time_limit_seconds: 1800,
  remaining_time_seconds: 1800,
  // Included directly on the session response so the test can navigate
  // straight to the shell (mirroring reading-mocked.spec.ts's
  // gotoReadingExam) without needing to prime sessionStorage's
  // listening_start_{id} fallback via the landing page first.
  audio_urls: AUDIO_URLS,
  questions: [
    {
      id: "listening-question-set-1",
      book_ref: "test-book",
      test_number: 1,
      exam_type: "academic",
      skill_area: "listening",
      passage_text: null,
      audio_s3_key: null,
      questions: LISTENING_QUESTIONS,
    },
  ],
};

function buildListeningSubmitResponse(answers: Record<string, string>) {
  // Shape must match ListeningSubmitResponse / the real exam service grade
  // payload — ReadingResultsView (reused for Listening) reads
  // per_question_result + section_breakdown, not the older section_scores /
  // results fields.
  const per_question_result: Record<
    string,
    { submitted_answer: string; correct_answer: string; is_correct: boolean }
  > = {};
  const section_breakdown: Record<string, { correct: number; total: number }> =
    {};

  for (let section = 1; section <= 4; section++) {
    section_breakdown[`section_${section}`] = {
      correct: 0,
      total: SECTION_QUESTION_COUNT,
    };
  }

  let totalCorrect = 0;
  for (const question of LISTENING_QUESTIONS) {
    const key = String(question.number);
    const submitted = answers[key] ?? "";
    const isCorrect = submitted === question.correct_answer;
    if (isCorrect) totalCorrect++;

    per_question_result[key] = {
      submitted_answer: submitted,
      correct_answer: String(question.correct_answer),
      is_correct: isCorrect,
    };

    const sectionKey = `section_${question.section_number}`;
    if (isCorrect) section_breakdown[sectionKey].correct++;
  }

  return {
    band_score: 6.0,
    raw_score: totalCorrect,
    per_question_result,
    section_breakdown,
  };
}

/** Mocks the Gateway's GET session and PUT listening/:id/submit endpoints,
 * plus the four section audio URLs, and exposes both the raw submit body
 * (to assert the scratch pad never leaks into it) and the parsed answers. */
async function mockListeningBackend(page: Page) {
  let submittedBody: Record<string, unknown> | null = null;

  await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}`, (route) =>
    withPreflight(route, (r) => fulfillJson(r, SESSION_RESPONSE)),
  );

  await page.route(
    `${GATEWAY_API_BASE}/listening/${SESSION_ID}/submit`,
    (route) =>
      withPreflight(route, (r) => {
        submittedBody = r.request().postDataJSON() as Record<string, unknown>;
        const answers = (submittedBody?.answers ?? {}) as Record<
          string,
          string
        >;
        return fulfillJson(r, buildListeningSubmitResponse(answers));
      }),
  );

  for (const url of AUDIO_URLS) {
    await page.route(url, (route) =>
      route.fulfill({
        status: 200,
        contentType: "audio/wav",
        body: SILENT_WAV_BUFFER,
      }),
    );
  }

  return {
    getSubmittedBody: () => submittedBody,
  };
}

async function gotoListeningExam(page: Page) {
  // domcontentloaded avoids hanging on Next.js "load" when the first shell
  // compile / HMR interrupts the document (ERR_ABORTED under waitUntil:load).
  await page.goto(`/exam/shell?session=${SESSION_ID}`, {
    waitUntil: "domcontentloaded",
  });
  await expect(page.getByText("Section 1 of 4")).toBeVisible({
    timeout: 30_000,
  });
}

async function ensureAudioPlaying(page: Page) {
  const playPause = page.getByTestId("locked-audio-play-pause");
  const playing = page.getByText("Playing", { exact: true });
  await playPause.waitFor({ state: "visible" });

  // Autoplay may still be in flight. Waiting first avoids the race where we
  // see "Ready to play", autoplay then succeeds, and our click toggles it
  // straight back to paused.
  try {
    await playing.waitFor({ state: "visible", timeout: 2_000 });
    return;
  } catch {
    // Autoplay was blocked — fall through to the explicit control.
  }

  await playPause.click();
  await expect(playing).toBeVisible();
}

/** The active section's <audio> element, addressed the same way
 * LockedAudioPlayer itself does — there is exactly one visible at a time
 * outside the answer-transfer phase. */
function activeAudio(page: Page) {
  return page.locator("audio");
}

async function endActiveSectionAudio(page: Page) {
  await activeAudio(page).evaluate((audio: HTMLAudioElement) => {
    audio.dispatchEvent(new Event("ended"));
  });
}

/**
 * Advance the 30s inter-section silence gap.
 *
 * Must use `runFor`, not `fastForward`: Playwright's fastForward only fires
 * each due timer at most once ("laptop lid" semantics), so a 30s jump would
 * tick the 1Hz silence interval a single time. `runFor` fires every interval
 * callback as time passes. Also: clock strings like "31s" are invalid —
 * only numbers, `mm:ss`, and `hh:mm:ss` are accepted.
 */
async function advanceSilenceGap(page: Page, ms = 30_000) {
  await page.clock.runFor(ms);
}

async function installPausedClock(page: Page) {
  // Let the page load with a living clock, then pause so silence-gap tests
  // can advance time manually. Installing already-paused (bare install())
  // can stall Next.js hydration that depends on rAF/timers.
  const start = new Date("2024-01-01T12:00:00Z");
  await page.clock.install({ time: start });
  await gotoListeningExam(page);
  await page.clock.pauseAt(new Date(start.getTime() + 1_000));
}

test.describe("Dalil Listening exam (mocked backend)", () => {
  // First hit of /exam/shell often pays for a cold Next compile; keep headroom
  // above the default 30s so a slow webServer does not flake the suite.
  test.describe.configure({ timeout: 60_000 });

  test("audio plays, section 1 ends, and Next Section appears", async ({
    page,
  }) => {
    await mockListeningBackend(page);
    await gotoListeningExam(page);

    // Autoplay may be blocked without a prior gesture; ensureAudioPlaying
    // waits for autoplay first, then clicks Play only if still idle.
    await ensureAudioPlaying(page);

    await endActiveSectionAudio(page);

    await expect(page.getByText("Section complete")).toBeVisible();
    await expect(page.getByTestId("next-section-button")).toBeVisible();
  });

  test("section 2 does not start until Next Section is clicked, then only after the 30s gap", async ({
    page,
  }) => {
    await mockListeningBackend(page);
    await installPausedClock(page);

    await endActiveSectionAudio(page);
    await expect(page.getByTestId("next-section-button")).toBeVisible();

    // Still section 1 until the candidate explicitly advances.
    await expect(page.getByText("Section 1 of 4")).toBeVisible();
    await page.waitForTimeout(500);
    await expect(page.getByText("Section 1 of 4")).toBeVisible();

    await page.getByTestId("next-section-button").click();
    await expect(page.getByTestId("silence-countdown")).toBeVisible();
    await expect(page.getByTestId("silence-countdown")).toContainText("00:30");

    // Partway through the gap, still not on section 2 yet.
    await advanceSilenceGap(page, 15_000);
    await expect(page.getByText("Section 1 of 4")).toBeVisible();
    await expect(page.getByTestId("silence-countdown")).toContainText("00:15");

    // Finish the remaining 15s — the tick that reaches 0 starts section 2.
    await advanceSilenceGap(page, 15_000);
    await expect(page.getByText("Section 2 of 4")).toBeVisible();
  });

  test("progress-bar drag and programmatic seek do not alter effective playback position", async ({
    page,
  }) => {
    await mockListeningBackend(page);
    await gotoListeningExam(page);
    await ensureAudioPlaying(page);

    // The progress indicator is read-only: it has no slider role and is
    // marked pointer-events: none, so a drag/click on it must not move
    // playback at all.
    const progress = page.getByRole("progressbar");
    const box = await progress.boundingBox();
    if (box) {
      await page.mouse.click(box.x + box.width * 0.9, box.y + box.height / 2);
    }

    const timeBefore = await page.getByTestId("locked-audio-time").innerText();

    // A programmatic seek (devtools-style) attempting to jump far ahead.
    await activeAudio(page).evaluate((audio: HTMLAudioElement) => {
      audio.currentTime = Math.max(30, audio.currentTime + 30);
    });

    // Give the component's timeupdate/seeking correction a beat to run.
    await page.waitForTimeout(200);

    const currentTimeAfter = await activeAudio(page).evaluate(
      (audio: HTMLAudioElement) => audio.currentTime,
    );
    const timeAfter = await page.getByTestId("locked-audio-time").innerText();

    // The displayed elapsed time should not have jumped by anything close
    // to the attempted 30s skip.
    expect(timeAfter).toBe(timeBefore);
    expect(currentTimeAfter).toBeLessThan(5);
  });

  test("questions stay answerable across section transitions, and the scratch pad is never sent on submit", async ({
    page,
  }) => {
    const backend = await mockListeningBackend(page);
    await installPausedClock(page);

    await page
      .getByTestId("listening-scratch-pad")
      .fill("private notes: the answer sounded like B");

    // Answer section 1's questions while it's active.
    await page
      .locator('[data-testid="question-1"] input[type="text"]')
      .fill("answer-1");

    await endActiveSectionAudio(page);
    await page.getByTestId("next-section-button").click();
    await advanceSilenceGap(page);
    await expect(page.getByText("Section 2 of 4")).toBeVisible();

    // Section 1's answer must have survived the transition even though
    // it's no longer the active section.
    await endActiveSectionAudio(page);
    await page.getByTestId("next-section-button").click();
    await advanceSilenceGap(page);
    await expect(page.getByText("Section 3 of 4")).toBeVisible();

    await page
      .locator('[data-testid="question-7"] input[type="text"]')
      .fill("answer-7");

    await endActiveSectionAudio(page);
    await page.getByTestId("next-section-button").click();
    await advanceSilenceGap(page);
    await expect(page.getByText("Section 4 of 4")).toBeVisible();

    await page
      .locator('[data-testid="question-10"] input[type="text"]')
      .fill("answer-10");

    // Section 4 ending drops straight into the transfer period.
    await endActiveSectionAudio(page);
    await expect(page.getByTestId("answer-transfer-countdown")).toBeVisible();

    // All previously-entered answers should still be visible during
    // transfer, proving they weren't lost across transitions.
    await expect(
      page.locator('[data-testid="question-1"] input[type="text"]'),
    ).toHaveValue("answer-1");
    await expect(
      page.locator('[data-testid="question-7"] input[type="text"]'),
    ).toHaveValue("answer-7");
    await expect(
      page.locator('[data-testid="question-10"] input[type="text"]'),
    ).toHaveValue("answer-10");

    await page.getByTestId("listening-submit-button").click();
    await expect(page).toHaveURL(
      new RegExp(`/exam/results\\?session=${SESSION_ID}&skill=Listening`),
    );

    const sent = backend.getSubmittedBody();
    expect(sent).not.toBeNull();
    expect(JSON.stringify(sent)).not.toContain("private notes");
    expect((sent as { answers: Record<string, string> }).answers).toEqual(
      expect.objectContaining({
        "1": "answer-1",
        "7": "answer-7",
        "10": "answer-10",
      }),
    );
  });

  test("results render all four section scores and highlight the weakest question type", async ({
    page,
  }) => {
    await mockListeningBackend(page);
    await installPausedClock(page);

    // Answer every question correctly so section scores are all full marks
    // except we deliberately leave section 3 short by one to exercise a
    // partial score too.
    for (let section = 1; section <= 4; section++) {
      const start = (section - 1) * SECTION_QUESTION_COUNT + 1;
      for (let n = start; n < start + SECTION_QUESTION_COUNT; n++) {
        if (section === 3 && n === start) continue; // leave one blank
        await page
          .locator(`[data-testid="question-${n}"] input[type="text"]`)
          .fill(`answer-${n}`);
      }

      await endActiveSectionAudio(page);
      if (section < 4) {
        await page.getByTestId("next-section-button").click();
        await advanceSilenceGap(page);
      }
    }

    await expect(page.getByTestId("answer-transfer-countdown")).toBeVisible();
    await page.getByTestId("listening-submit-button").click();

    await expect(page).toHaveURL(
      new RegExp(`/exam/results\\?session=${SESSION_ID}&skill=Listening`),
    );
    await expect(page.getByTestId("listening-results-view")).toBeVisible();
    await expect(page.getByTestId("listening-band-score")).toBeVisible();

    for (let section = 1; section <= 4; section++) {
      await expect(
        page.getByTestId(`section-bar-section_${section}`),
      ).toBeVisible();
    }
    await expect(page.getByTestId("section-bar-section_3")).toContainText(
      `${SECTION_QUESTION_COUNT - 1}/${SECTION_QUESTION_COUNT}`,
    );

    await expect(page.getByTestId("question-type-breakdown")).toBeVisible();
    await expect(
      page.getByTestId("breakdown-fill_in_blank"),
    ).toHaveAttribute("data-weakest", "true");

    await page.getByTestId("practice-listening-again-button").click();
    await expect(page).toHaveURL(/\/exam$/);
  });
});


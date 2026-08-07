# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: Listening mocked.spec.ts >> GOA Listening exam (mocked backend) >> audio plays, section 1 ends, and Next Section appears
- Location: test\e2e\Listening mocked.spec.ts:212:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Section 1 of 4')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('Section 1 of 4')

```

```yaml
- heading "404" [level=1]
- heading "This page could not be found." [level=2]
- alert
```

# Test source

```ts
  84  |   time_limit_seconds: 1800,
  85  |   remaining_time_seconds: 1800,
  86  |   // Included directly on the session response so the test can navigate
  87  |   // straight to the shell (mirroring reading-mocked.spec.ts's
  88  |   // gotoReadingExam) without needing to prime sessionStorage's
  89  |   // listening_start_{id} fallback via the landing page first.
  90  |   audio_urls: AUDIO_URLS,
  91  |   questions: [
  92  |     {
  93  |       id: "listening-question-set-1",
  94  |       book_ref: "test-book",
  95  |       test_number: 1,
  96  |       exam_type: "academic",
  97  |       skill_area: "listening",
  98  |       passage_text: null,
  99  |       audio_s3_key: null,
  100 |       questions: LISTENING_QUESTIONS,
  101 |     },
  102 |   ],
  103 | };
  104 | 
  105 | function buildListeningSubmitResponse(answers: Record<string, string>) {
  106 |   const sectionScores: Record<string, string> = {};
  107 |   for (let section = 1; section <= 4; section++) {
  108 |     const start = (section - 1) * SECTION_QUESTION_COUNT + 1;
  109 |     let correct = 0;
  110 |     for (let n = start; n < start + SECTION_QUESTION_COUNT; n++) {
  111 |       if (answers[String(n)] === `answer-${n}`) correct++;
  112 |     }
  113 |     sectionScores[`section_${section}`] =
  114 |       `${correct}/${SECTION_QUESTION_COUNT}`;
  115 |   }
  116 | 
  117 |   // Deliberately make sentence_completion the (only, hence weakest)
  118 |   // question type, with a couple of misses, so the breakdown has something
  119 |   // meaningful to highlight.
  120 |   const totalCorrect = Object.values(answers).filter(
  121 |     (v, i) => v === `answer-${i + 1}`,
  122 |   ).length;
  123 | 
  124 |   return {
  125 |     band_score: 6.0,
  126 |     raw_score: totalCorrect,
  127 |     section_scores: sectionScores,
  128 |     question_type_breakdown: {
  129 |       sentence_completion: {
  130 |         correct: totalCorrect,
  131 |         total: LISTENING_QUESTIONS.length,
  132 |         weakest: true,
  133 |       },
  134 |     },
  135 |     results: LISTENING_QUESTIONS.map((q) => ({
  136 |       number: q.number,
  137 |       correct: answers[String(q.number)] === q.correct_answer,
  138 |       user_answer: answers[String(q.number)] ?? null,
  139 |       correct_answer: q.correct_answer,
  140 |     })),
  141 |   };
  142 | }
  143 | 
  144 | /** Mocks the Gateway's GET session and PUT listening/:id/submit endpoints,
  145 |  * plus the four section audio URLs, and exposes both the raw submit body
  146 |  * (to assert the scratch pad never leaks into it) and the parsed answers. */
  147 | async function mockListeningBackend(page: Page) {
  148 |   let submittedBody: Record<string, unknown> | null = null;
  149 | 
  150 |   await page.route(`${GATEWAY_API_BASE}/sessions/${SESSION_ID}`, (route) =>
  151 |     withPreflight(route, (r) => fulfillJson(r, SESSION_RESPONSE)),
  152 |   );
  153 | 
  154 |   await page.route(
  155 |     `${GATEWAY_API_BASE}/listening/${SESSION_ID}/submit`,
  156 |     (route) =>
  157 |       withPreflight(route, (r) => {
  158 |         submittedBody = r.request().postDataJSON() as Record<string, unknown>;
  159 |         const answers = (submittedBody?.answers ?? {}) as Record<
  160 |           string,
  161 |           string
  162 |         >;
  163 |         return fulfillJson(r, buildListeningSubmitResponse(answers));
  164 |       }),
  165 |   );
  166 | 
  167 |   for (const url of AUDIO_URLS) {
  168 |     await page.route(url, (route) =>
  169 |       route.fulfill({
  170 |         status: 200,
  171 |         contentType: "audio/wav",
  172 |         body: Buffer.from(SILENT_WAV_BASE64, "base64"),
  173 |       }),
  174 |     );
  175 |   }
  176 | 
  177 |   return {
  178 |     getSubmittedBody: () => submittedBody,
  179 |   };
  180 | }
  181 | 
  182 | async function gotoListeningExam(page: Page) {
  183 |   await page.goto(`/exam/shell?session=${SESSION_ID}`);
> 184 |   await expect(page.getByText("Section 1 of 4")).toBeVisible();
      |                                                  ^ Error: expect(locator).toBeVisible() failed
  185 | }
  186 | 
  187 | async function clickPlayPauseIfReady(page: Page) {
  188 |   const playPause = page.getByTestId("locked-audio-play-pause");
  189 |   await playPause.waitFor({ state: "visible" });
  190 |   await expect(playPause).toBeEnabled();
  191 |   await page.waitForTimeout(50);
  192 | 
  193 |   if (await page.getByText("Ready to play").isVisible()) {
  194 |     await playPause.click();
  195 |   }
  196 | }
  197 | 
  198 | /** The active section's <audio> element, addressed the same way
  199 |  * LockedAudioPlayer itself does — there is exactly one visible at a time
  200 |  * outside the answer-transfer phase. */
  201 | function activeAudio(page: Page) {
  202 |   return page.locator("audio");
  203 | }
  204 | 
  205 | async function endActiveSectionAudio(page: Page) {
  206 |   await activeAudio(page).evaluate((audio: HTMLAudioElement) => {
  207 |     audio.dispatchEvent(new Event("ended"));
  208 |   });
  209 | }
  210 | 
  211 | test.describe("GOA Listening exam (mocked backend)", () => {
  212 |   test("audio plays, section 1 ends, and Next Section appears", async ({
  213 |     page,
  214 |   }) => {
  215 |     await mockListeningBackend(page);
  216 |     await gotoListeningExam(page);
  217 | 
  218 |     // Autoplay may be blocked by the browser without a prior user gesture;
  219 |     // fall back to the visible control exactly as a candidate would, then
  220 |     // confirm playback state is reflected in the UI either way.
  221 |     await clickPlayPauseIfReady(page);
  222 |     await expect(page.getByText("Playing")).toBeVisible();
  223 | 
  224 |     await endActiveSectionAudio(page);
  225 | 
  226 |     await expect(page.getByText("Section complete")).toBeVisible();
  227 |     await expect(page.getByTestId("next-section-button")).toBeVisible();
  228 |   });
  229 | 
  230 |   test("section 2 does not start until Next Section is clicked, then only after the 30s gap", async ({
  231 |     page,
  232 |   }) => {
  233 |     await mockListeningBackend(page);
  234 |     await page.clock.install();
  235 |     await gotoListeningExam(page);
  236 | 
  237 |     await endActiveSectionAudio(page);
  238 |     await expect(page.getByTestId("next-section-button")).toBeVisible();
  239 | 
  240 |     // Still section 1 until the candidate explicitly advances.
  241 |     await expect(page.getByText("Section 1 of 4")).toBeVisible();
  242 |     await page.waitForTimeout(500);
  243 |     await expect(page.getByText("Section 1 of 4")).toBeVisible();
  244 | 
  245 |     await page.getByTestId("next-section-button").click();
  246 |     await expect(page.getByTestId("silence-countdown")).toBeVisible();
  247 |     await expect(page.getByTestId("silence-countdown")).toContainText("0:30");
  248 | 
  249 |     // Partway through the gap, still not on section 2 yet.
  250 |     await page.clock.fastForward(15_000);
  251 |     await expect(page.getByText("Section 1 of 4")).toBeVisible();
  252 | 
  253 |     await page.clock.fastForward(15_000);
  254 |     await expect(page.getByText("Section 2 of 4")).toBeVisible();
  255 |   });
  256 | 
  257 |   test("progress-bar drag and programmatic seek do not alter effective playback position", async ({
  258 |     page,
  259 |   }) => {
  260 |     await mockListeningBackend(page);
  261 |     await gotoListeningExam(page);
  262 |     await clickPlayPauseIfReady(page);
  263 | 
  264 |     // The progress indicator is read-only: it has no slider role and is
  265 |     // marked pointer-events: none, so a drag/click on it must not move
  266 |     // playback at all.
  267 |     const progress = page.getByRole("progressbar");
  268 |     const box = await progress.boundingBox();
  269 |     if (box) {
  270 |       await page.mouse.click(box.x + box.width * 0.9, box.y + box.height / 2);
  271 |     }
  272 | 
  273 |     const timeBefore = await page.getByTestId("locked-audio-time").innerText();
  274 | 
  275 |     // A programmatic seek (devtools-style) attempting to jump far ahead.
  276 |     await activeAudio(page).evaluate((audio: HTMLAudioElement) => {
  277 |       audio.currentTime = Math.max(30, audio.currentTime + 30);
  278 |     });
  279 | 
  280 |     // Give the component's timeupdate/seeking correction a beat to run.
  281 |     await page.waitForTimeout(200);
  282 | 
  283 |     const currentTimeAfter = await activeAudio(page).evaluate(
  284 |       (audio: HTMLAudioElement) => audio.currentTime,
```
import { test, expect } from "./fixtures/auth";

test("completes a spoken three-part interviewer session", async ({ page }) => {
  await page.addInitScript(() => {
    class MockMediaRecorder {
      static isTypeSupported() {
        return true;
      }
      state = "inactive";
      mimeType = "audio/webm;codecs=opus";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      private listeners: Array<() => void> = [];
      constructor(_stream: MediaStream, _options?: MediaRecorderOptions) {}
      start() {
        this.state = "recording";
      }
      stop() {
        this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
        this.state = "inactive";
        this.listeners.splice(0).forEach((listener) => listener());
      }
      addEventListener(type: string, listener: () => void) {
        if (type === "stop") this.listeners.push(listener);
      }
    }
    class InstantAudio {
      onended: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      currentTime = 0;
      constructor(_url?: string) {}
      play() {
        setTimeout(() => this.onended?.(new Event("ended")), 0);
        return Promise.resolve();
      }
      pause() {}
    }

    class InterviewWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      readyState = InterviewWebSocket.CONNECTING;
      binaryType = "arraybuffer";
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      private phase = "init";
      private listeners = new Map<string, Array<(event: Event) => void>>();

      // Next's development HMR client also observes WebSocket through the DOM
      // EventTarget API. Keep this test double compatible so it doesn't crash
      // the page before the speaking component mounts.
      addEventListener(type: string, listener: (event: Event) => void) {
        this.listeners.set(type, [
          ...(this.listeners.get(type) ?? []),
          listener,
        ]);
      }
      removeEventListener(type: string, listener: (event: Event) => void) {
        this.listeners.set(
          type,
          (this.listeners.get(type) ?? []).filter((item) => item !== listener),
        );
      }
      dispatchEvent() {
        return true;
      }

      constructor(_url: string) {
        setTimeout(() => {
          this.readyState = InterviewWebSocket.OPEN;
          const event = new Event("open");
          this.onopen?.(event);
          this.listeners.get("open")?.forEach((listener) => listener(event));
        }, 0);
      }

      private json(frame: Record<string, unknown>) {
        this.onmessage?.(
          new MessageEvent("message", { data: JSON.stringify(frame) }),
        );
      }

      private examiner(
        turnId: string,
        part: number,
        questionId: string,
        text: string,
        expectsResponse: boolean,
      ) {
        this.json({
          type: "examiner_turn",
          turn_id: turnId,
          part,
          question_id: questionId,
          text,
          expects_response: expectsResponse,
        });
        this.onmessage?.(
          new MessageEvent("message", { data: new ArrayBuffer(16) }),
        );
        this.json({ type: "examiner_audio_end", turn_id: turnId });
      }

      send(payload: string | ArrayBuffer | Blob) {
        if (typeof payload !== "string") return;
        const frame = JSON.parse(payload);
        if (frame.type === "session_init") {
          this.json({
            type: "session_started",
            session_id: "browser-e2e-session",
            resumed: false,
          });
          this.json({
            type: "part_change",
            part: 1,
            part_label: "Introduction and interview",
            expected_duration_s: 300,
          });
          this.examiner(
            "t001",
            1,
            "script.part1.intro",
            "Good morning. We will begin with questions about you.",
            false,
          );
          this.phase = "intro";
        } else if (frame.type === "ready" && this.phase === "intro") {
          this.examiner(
            "t002",
            1,
            "p1.home.q1",
            "What do you like about your home?",
            true,
          );
          this.phase = "part1";
        } else if (frame.type === "ready" && this.phase === "cue") {
          this.json({
            type: "prep_start",
            duration_s: 1,
            ends_at: new Date(Date.now() + 30).toISOString(),
          });
          setTimeout(() => {
            this.json({ type: "prep_end" });
            this.json({
              type: "long_turn_start",
              min_s: 0,
              max_s: 120,
              ends_at: new Date(Date.now() + 120_000).toISOString(),
            });
            this.phase = "long-turn";
          }, 40);
        } else if (frame.type === "audio_end") {
          this.advanceAfterAnswer();
        }
      }

      private advanceAfterAnswer() {
        this.json({
          type: "transcript",
          text: `Candidate answer in ${this.phase}.`,
          isFinal: true,
        });
        if (this.phase === "part1") {
          this.json({
            type: "part_change",
            part: 2,
            part_label: "Long turn",
            expected_duration_s: 240,
          });
          this.examiner(
            "t004",
            2,
            "script.part2.transition",
            "Now I am going to give you a topic.",
            false,
          );
          this.json({
            type: "cue_card",
            cue_id: "p2.skill",
            topic: "Describe a skill you would like to learn.",
            prompts: [
              "what it is",
              "how you would learn it",
              "how difficult it might be",
            ],
            closing_prompt: "Explain why you want to learn it",
          });
          this.examiner(
            "t005",
            2,
            "p2.skill",
            "Describe a skill you would like to learn.",
            false,
          );
          this.phase = "cue";
        } else if (this.phase === "long-turn") {
          this.examiner(
            "t007",
            2,
            "p2.skill.r1",
            "Do many people you know have this skill?",
            true,
          );
          this.phase = "rounding";
        } else if (this.phase === "rounding") {
          this.json({
            type: "part_change",
            part: 3,
            part_label: "Discussion",
            expected_duration_s: 300,
          });
          this.examiner(
            "t009",
            3,
            "script.part3.transition",
            "Now let us discuss this topic more generally.",
            false,
          );
          this.examiner(
            "t010",
            3,
            "p3.skills.q1",
            "How has the way people learn skills changed?",
            true,
          );
          this.phase = "part3-first";
        } else if (this.phase === "part3-first") {
          this.examiner(
            "t012",
            3,
            "p3.generated.1",
            "Why might flexibility matter to adult learners?",
            true,
          );
          this.phase = "part3-followup";
        } else if (this.phase === "part3-followup") {
          this.examiner(
            "t014",
            3,
            "script.closing",
            "That is the end of the speaking practice. Thank you.",
            false,
          );
          this.json({
            type: "session_complete",
            turn_count: 14,
            total_candidate_s: 90,
          });
          this.json({
            type: "evaluation",
            status: "completed",
            completed_count: 4,
            overall_band: 7,
            overall_feedback:
              "Your answers were developed across all three parts.",
            dimensions: {
              "Fluency and Coherence": {
                criterion: "Fluency and Coherence",
                band: 7,
                feedback: "Clear flow",
              },
              "Lexical Resource": {
                criterion: "Lexical Resource",
                band: 7,
                feedback: "Good range",
              },
              "Grammatical Range and Accuracy": {
                criterion: "Grammatical Range and Accuracy",
                band: 7,
                feedback: "Varied structures",
              },
              Pronunciation: {
                criterion: "Pronunciation",
                band: 7,
                feedback: "Clear phrasing",
              },
            },
          });
          this.phase = "complete";
        }
      }

      close() {
        this.readyState = InterviewWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close", { code: 1000 }));
      }
    }

    Object.defineProperty(window, "Audio", {
      configurable: true,
      value: InstantAudio,
    });
    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      value: MockMediaRecorder,
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
      },
    });
    Object.defineProperty(window, "InterviewWebSocketMock", {
      configurable: true,
      value: InterviewWebSocket,
    });
  });

  await page.context().grantPermissions(["microphone"]);
  await page.goto("/practice/speaking");
  // Leave Next's development HMR socket alone during boot, then install the
  // speaking transport double once the application has hydrated.
  await page.evaluate(() => {
    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      value: (window as unknown as { InterviewWebSocketMock: typeof WebSocket })
        .InterviewWebSocketMock,
    });
  });
  await expect(page.getByTestId("start-speaking-button")).toBeEnabled();
  // The profile hook settles immediately after hydration and replaces this
  // subtree once. Wait for that render so the click targets the attached node.
  await page.waitForTimeout(250);
  await page.getByTestId("start-speaking-button").click();

  await expect(page.getByTestId("examiner-turn")).toContainText(
    "What do you like about your home?",
  );
  await page.getByTestId("stop-speaking-button").click();

  await expect(page.getByTestId("speaking-cue-card")).toContainText(
    "Describe a skill",
  );
  await expect(page.getByTestId("speaking-part-indicator")).toContainText(
    "Long turn",
  );
  await page.getByTestId("stop-speaking-button").click();

  await expect(page.getByTestId("examiner-turn")).toContainText(
    "Do many people",
  );
  await page.getByTestId("stop-speaking-button").click();

  await expect(page.getByTestId("speaking-part-indicator")).toContainText(
    "Discussion",
  );
  await expect(page.getByTestId("examiner-turn")).toContainText(
    "How has the way people learn skills changed?",
  );
  await page.getByTestId("stop-speaking-button").click();

  await expect(page.getByTestId("examiner-turn")).toContainText(
    "Why might flexibility matter",
  );
  await page.getByTestId("stop-speaking-button").click();

  await expect(page.getByText("IELTS Speaking Band Score")).toBeVisible();
  await expect(page.getByText("Estimated Overall Band")).toBeVisible();
  await expect(
    page.getByText("Your answers were developed across all three parts."),
  ).toBeVisible();
  await expect(page.getByTestId("live-transcript")).toContainText("Part 3");
});

import { test, expect } from "./fixtures/auth";

/**
 * A reload during the examiner's greeting used to kill the interview.
 *
 * The client stores the session id and offers it back as `resumeSessionId`; the
 * server resumed the session but emitted no examiner turn for the two states
 * that are waiting on `ready` — the greeting and the cue card. The client only
 * sends `ready` in response to an examiner turn, so both sides waited on each
 * other and the examiner never spoke again.
 *
 * The fake socket below replays what the fixed server now sends. What is under
 * test here is the client half of that contract: that a replayed greeting is
 * enough to get the interview moving again.
 */
test("the examiner picks the interview back up after a reload during the greeting", async ({ page }) => {
  await page.addInitScript(() => {
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

    class ResumingWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;
      readyState = ResumingWebSocket.CONNECTING;
      binaryType = "arraybuffer";
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      private phase = "init";

      constructor(_url: string) {
        setTimeout(() => {
          this.readyState = ResumingWebSocket.OPEN;
          this.onopen?.(new Event("open"));
        }, 0);
      }

      private json(frame: Record<string, unknown>) {
        this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(frame) }));
      }

      private examiner(turnId: string, part: number, questionId: string, text: string, expectsResponse: boolean) {
        this.json({ type: "examiner_turn", turn_id: turnId, part, question_id: questionId, text, expects_response: expectsResponse });
        this.onmessage?.(new MessageEvent("message", { data: new ArrayBuffer(16) }));
        this.json({ type: "examiner_audio_end", turn_id: turnId });
      }

      send(payload: string | ArrayBuffer | Blob) {
        if (typeof payload !== "string") return;
        const frame = JSON.parse(payload);

        if (frame.type === "session_init" && frame.resumeSessionId) {
          // The resume path, as the server emits it: the acknowledgement, the
          // state the interview is in, and the turn it is waiting on — the
          // greeting, which asks for no speech.
          (window as unknown as { __resumedWith?: string }).__resumedWith = frame.resumeSessionId;
          this.json({ type: "session_started", session_id: frame.resumeSessionId, resumed: true });
          this.json({ type: "session_resumed", part: 1, text: "part1_intro" });
          this.examiner("t001", 1, "script.part1.intro", "Good morning. This is your IELTS-style speaking practice.", false);
          this.phase = "intro";
          return;
        }

        if (frame.type === "session_init") {
          this.json({ type: "session_started", session_id: "resume-e2e-session", resumed: false });
          this.json({ type: "part_change", part: 1, part_label: "Introduction and interview", expected_duration_s: 300 });
          this.examiner("t001", 1, "script.part1.intro", "Good morning. This is your IELTS-style speaking practice.", false);
          this.phase = "intro";
          return;
        }

        if (frame.type === "ready" && this.phase === "intro") {
          this.examiner("t002", 1, "p1.hometown.q1", "Where is your hometown?", true);
          this.phase = "part1";
        }
      }

      close() {
        this.readyState = ResumingWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close", { code: 1000 }));
      }
    }

    Object.defineProperty(window, "Audio", { configurable: true, value: InstantAudio });
    Object.defineProperty(window, "WebSocket", { configurable: true, value: ResumingWebSocket });
  });

  await page.context().grantPermissions(["microphone"]);
  await page.goto("/practice/speaking");
  await page.getByTestId("start-speaking-button").click();
  await expect(page.getByTestId("examiner-turn")).toContainText("Where is your hometown?");

  // The candidate reloads mid-interview. The session id survives in
  // localStorage, so the next attempt is a resume rather than a new interview.
  await page.reload();
  await page.getByTestId("start-speaking-button").click();

  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __resumedWith?: string }).__resumedWith))
    .toBe("resume-e2e-session");

  // The replayed greeting has to carry the interview forward on its own: the
  // candidate is not asked to do anything to unstick it.
  await expect(page.getByTestId("examiner-turn")).toContainText("Where is your hometown?");
  await expect(page.getByTestId("speaking-part-indicator")).toContainText("Introduction and interview");
});

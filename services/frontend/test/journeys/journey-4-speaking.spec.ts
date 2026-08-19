/**
 * GOA-030 Journey 4 — start a speaking session, speak, receive transcript.
 *
 * Acceptance criterion:
 *
 *   "Start a speaking session -> speak a sentence -> receive transcript +
 *    evaluation"
 *
 * Three things about this journey are deliberate.
 *
 * 1. It drives protocol v3, because that is what the product now serves.
 *    services/speaking/internal/speaking/router.go puts the three-part interview
 *    on /ws and keeps the legacy monologue on /ws/v2 "only for controlled
 *    rollback"; the Gateway proxies /api/speaking/ws to the former. A journey
 *    written against v2 frames would receive a typed protocol refusal.
 *
 * 2. It ends the session with `abandon` rather than playing all three parts.
 *    A full interview is 11-14 minutes BY DESIGN -- the 60-second preparation
 *    timer is a scoring rule the server explicitly refuses to let a client skip,
 *    and the long turn has a 60-second floor. `abandon` is a first-class
 *    transition that scores what exists and records the rest as absent (never as
 *    zero), so the whole pipeline runs inside a bounded window without a
 *    test-only timing override weakening a scoring rule. The trade is stated
 *    rather than hidden: Part 3's adaptive generation is NOT covered here.
 *
 * 3. The socket is driven from inside the browser, not from Node. The cohesion
 *    requirement is that a browser can reach it; opening the WebSocket from the
 *    page context proves the handshake, the cookie and the Gateway's JWT check
 *    at upgrade time all work the way they do for a real user. It also needs no
 *    new dependency.
 *
 * This journey is the one that found the identity defect: the Gateway relayed
 * session_init byte-for-byte, so the client-supplied userId decided both which
 * account a session was persisted under and which key the daily quota counted
 * against. See services/gateway/handlers/speaking_ws.go.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect, step, signInBrowser, GATEWAY_URL } from "./fixtures/live";

const JOURNEY = "journey-4-speaking";

// 16 kHz, 16-bit, mono -- the format stt.go declares and the sidecar decodes.
// Real spoken English, not synthetic noise: Whisper returns an empty transcript
// for noise, so the swarm grades nothing, the run finishes suspiciously fast and
// the numbers describe a pipeline that never did any work.
const FIXTURE = join(process.cwd(), "..", "..", "perf", "fixtures", "ielts-part2-answer.16k.pcm");
const BYTES_PER_SECOND = 16000 * 2;
const ANSWER_SECONDS = 8;

interface SocketOutcome {
  frames: string[];
  transcripts: string[];
  sessionComplete: Record<string, unknown> | null;
  error: string | null;
  upgradeFailed: boolean;
}

test.describe("Journey 4 — speaking interview", () => {
  test("runs a protocol-v3 interview and receives a real transcript", async ({
    page,
    api,
    liveUser,
  }) => {
    await step(JOURNEY, "sign the browser in", async () => {
      await signInBrowser(page, liveUser);
    });

    await step(JOURNEY, "load the speaking practice page", async () => {
      await page.goto("/practice/speaking");
      await expect(page.getByTestId("speaking-panel")).toBeVisible({ timeout: 60_000 });
    });

    const clip = readFileSync(FIXTURE).subarray(0, ANSWER_SECONDS * BYTES_PER_SECOND);
    const clipBase64 = clip.toString("base64");

    const outcome = await step(JOURNEY, "drive a v3 interview over the socket", async () =>
      page.evaluate(
        async ({ gateway, audioBase64 }) => {
          const binary = Uint8Array.from(atob(audioBase64), (c) => c.charCodeAt(0));
          const CHUNK = 16000; // ~0.5s, roughly what MediaRecorder emits

          return await new Promise<SocketOutcome>((resolve) => {
            const result: SocketOutcome = {
              frames: [],
              transcripts: [],
              sessionComplete: null,
              error: null,
              upgradeFailed: false,
            };
            let candidateTurns = 0;
            const MAX_TURNS = 2;

            // The cookie rides the handshake: localhost:3000 and localhost:8080
            // differ only by port, so they are same-site and a SameSite=Lax
            // cookie is sent. That is also how the real client authenticates.
            const socket = new WebSocket(`${gateway.replace(/^http/, "ws")}/api/speaking/ws`);
            socket.binaryType = "arraybuffer";

            const finish = () => {
              try {
                socket.close();
              } catch {
                /* already closing */
              }
              resolve(result);
            };
            const guard = setTimeout(() => {
              result.error ??= "timed out waiting for session_complete";
              finish();
            }, 180_000);

            socket.onerror = () => {
              result.upgradeFailed = true;
              result.error ??= "socket error before or during the session";
              clearTimeout(guard);
              finish();
            };

            socket.onopen = () => {
              socket.send(
                JSON.stringify({
                  type: "session_init",
                  protocolVersion: 3,
                  // Deliberately a value the caller controls. The Gateway must
                  // override it with the JWT subject; Journey 4's DB assertion
                  // below is what proves it did.
                  userId: "client-supplied-should-be-ignored",
                  audioFormat: "audio/pcm;rate=16000",
                }),
              );
            };

            socket.onmessage = (event) => {
              if (event.data instanceof ArrayBuffer) {
                result.frames.push("examiner_audio");
                return;
              }
              let frame: any;
              try {
                frame = JSON.parse(event.data as string);
              } catch {
                return;
              }
              result.frames.push(frame.type);

              if (frame.type === "session_started") {
                socket.send(JSON.stringify({ type: "ready" }));
              } else if (frame.type === "transcript" && frame.isFinal) {
                result.transcripts.push(String(frame.text ?? ""));
              } else if (frame.type === "examiner_turn" && frame.expects_response) {
                if (candidateTurns >= MAX_TURNS) {
                  socket.send(JSON.stringify({ type: "abandon" }));
                  return;
                }
                for (let offset = 0; offset < binary.length; offset += CHUNK) {
                  socket.send(binary.subarray(offset, Math.min(offset + CHUNK, binary.length)));
                }
                socket.send(JSON.stringify({ type: "audio_end" }));
                candidateTurns += 1;
              } else if (frame.type === "session_complete" || frame.type === "evaluation") {
                result.sessionComplete = frame;
                clearTimeout(guard);
                finish();
              } else if (frame.type === "error" || frame.type === "policy_error") {
                result.error = JSON.stringify(frame);
                clearTimeout(guard);
                finish();
              }
            };
          });
        },
        { gateway: GATEWAY_URL, audioBase64: clipBase64 },
      ),
    );

    await step(JOURNEY, "check the interview ran and produced speech", async () => {
      expect(
        outcome.upgradeFailed,
        "the WebSocket never opened. The Gateway rejects the upgrade when the " +
          "access_token cookie is missing or invalid at handshake time.",
      ).toBe(false);
      expect(outcome.error, `session ended with an error: ${outcome.error}`).toBeNull();

      // v3-specific frames. Their absence means a v2 handler answered, which
      // would make everything below meaningless.
      expect(outcome.frames, "no part_change frame -- this is not protocol v3").toContain(
        "part_change",
      );
      expect(outcome.frames).toContain("examiner_turn");
      expect(
        outcome.frames.filter((f) => f === "examiner_audio").length,
        "the examiner never spoke: no binary TTS frames arrived",
      ).toBeGreaterThan(0);

      // The AC's "receive transcript". Asserted as real words rather than a
      // non-empty string: an empty or whitespace transcript is exactly what a
      // pipeline that decoded noise produces, and it must not read as a pass.
      expect(
        outcome.transcripts.length,
        "no final transcript arrived, so STT produced nothing for real speech",
      ).toBeGreaterThan(0);
      const spoken = outcome.transcripts.join(" ").trim();
      expect(
        spoken.split(/\s+/).filter(Boolean).length,
        `transcript was empty or near-empty (${JSON.stringify(spoken)}). ` +
          "That is what decoding a compressed container as raw PCM looks like.",
      ).toBeGreaterThan(3);

      expect(outcome.sessionComplete, "session never completed").toBeTruthy();
      // Ended via abandon, so the server must mark it partial rather than
      // presenting a truncated interview as a whole one.
      expect(outcome.sessionComplete).toHaveProperty("partial", true);
    });

    await step(JOURNEY, "verify the session is attributed to the token's user", async () => {
      // This is the security assertion. The client sent
      // "client-supplied-should-be-ignored" in session_init; the session must
      // appear in THIS user's history, listed by an endpoint that takes its
      // userId from the JWT and not from the caller.
      // Polled, not read once. `session_complete` is emitted when the interview
      // ends; scoring and the row write finish just after it, so a single
      // immediate read races the persist and reports a missing session that
      // arrives 200ms later. The bound is what makes this an assertion rather
      // than a sleep: if it never lands, the journey still fails.
      let sessions: Array<Record<string, any>> = [];
      await expect
        .poll(
          async () => {
            const response = await api.get(`${GATEWAY_URL}/api/speaking/sessions`, {
              headers: { Authorization: `Bearer ${liveUser.accessToken}` },
            });
            if (!response.ok()) return -1;
            sessions = (await response.json()) as Array<Record<string, any>>;
            return sessions.length;
          },
          {
            timeout: 60_000,
            intervals: [500, 1000, 2000, 5000],
            message:
              "the completed interview never appeared in the signed-in user's " +
              "history. Either it was persisted under the client-supplied userId " +
              "(the Gateway is not asserting X-User-Id), or it was not persisted.",
          },
        )
        .toBeGreaterThan(0);

      expect(sessions[0].question_type).toBe("full_interview");

      // GOA-134's band contract, on the speaking side. An abandoned session has
      // too few completed criteria to carry a band, and "not scored" must be
      // representable as null rather than as 0.0.
      const band = sessions[0].overall_band;
      if (band !== null && band !== undefined) {
        expect(band).toBeGreaterThanOrEqual(1);
        expect(band).toBeLessThanOrEqual(9);
      }
      expect(
        band,
        "a partial session reported band 0. 'Not scored' and 'scored zero' " +
          "are different facts and must not collapse (BUG-055).",
      ).not.toBe(0);
    });
  });
});

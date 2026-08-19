// GOA-036 — speaking scenario, protocol v3.
//
// This replaces the v2 drive in perf/speaking-load.js. That script sends
// {type:"session_init", questionPrompt, questionType} and waits for
// transcript/criterion/evaluation frames, which was correct until 2026-08-09:
// router.go now serves the three-part interview on /ws and keeps the legacy
// monologue on /ws/v2 "only for controlled rollback". The Gateway proxies
// /api/speaking/ws to the former, so the v2 script receives a typed protocol
// refusal and measures nothing. speaking-load.js is retained, repointed at
// /ws/v2, as the regression series against slo.go.
//
// Sessions end with `abandon` after a bounded number of Part 1 turns. A full
// interview is 11-14 minutes BY DESIGN -- the 60-second preparation timer is a
// scoring rule the server refuses to let a client skip, and the long turn has a
// 60-second floor -- so a 10-minute run at any concurrency would contain at most
// one partial session per VU and the percentile would describe the timer rather
// than the system. `abandon` is a first-class transition that scores what exists
// and records the rest as absent, so the measured path is still
// upgrade -> proxy -> bank -> TTS -> STT -> persist.
//
// What this does NOT measure, stated rather than implied: Part 3 adaptive
// generation, and the prep/long-turn timers themselves.

import ws from "k6/ws";
import { check } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";

const GATEWAY_WS = __ENV.GATEWAY_WS || "ws://localhost:8080";
const AUDIO_SECONDS = parseInt(__ENV.AUDIO_SECONDS || "8", 10);
const TURNS = parseInt(__ENV.SPEAKING_TURNS || "2", 10);

export const wsUpgradeOk = new Rate("goa_speaking_ws_upgrade_success");
export const timeToFirstTranscript = new Trend("goa_speaking_time_to_first_transcript_ms", true);
export const timeToComplete = new Trend("goa_speaking_time_to_complete_ms", true);
export const transcriptsReceived = new Counter("goa_speaking_transcripts");
export const emptyTranscripts = new Counter("goa_speaking_empty_transcripts");
export const speakingErrors = new Counter("goa_speaking_errors");

// 16 kHz, 16-bit, mono -- the format stt.go declares and the sidecar decodes.
const BYTES_PER_SECOND = 16000 * 2;
const CHUNK_BYTES = 16000; // ~0.5s, roughly what MediaRecorder emits

// Real spoken English. Synthetic noise is worse than useless here: Whisper
// returns an empty transcript for it, the run finishes suspiciously fast, and
// the numbers describe a pipeline that never did any work.
const FIXTURE = open("../fixtures/ielts-part2-answer.16k.pcm", "b");
const CLIP = FIXTURE.slice(0, Math.min(AUDIO_SECONDS * BYTES_PER_SECOND, FIXTURE.byteLength));

export function speakingScenario(tokens) {
  const token = tokens[(__VU - 1) % tokens.length];
  const url = `${GATEWAY_WS}/api/speaking/ws`;

  let start = 0;
  let sawTranscript = false;
  let candidateTurns = 0;

  const res = ws.connect(url, { headers: { Cookie: `access_token=${token}` } }, function (socket) {
    socket.on("open", function () {
      start = Date.now();
      socket.send(
        JSON.stringify({
          type: "session_init",
          protocolVersion: 3,
          // The Gateway overrides this with the JWT subject (GOA-030). Left as
          // a placeholder deliberately: if it ever starts deciding attribution
          // again, every k6 session would land under one id and the quota would
          // stop applying, which is the regression worth noticing.
          userId: `k6-speaking-${__VU}`,
          audioFormat: "audio/pcm;rate=16000",
        }),
      );
    });

    socket.on("binaryMessage", function () {
      // Examiner TTS. Counted only through the frames that matter below.
    });

    socket.on("message", function (raw) {
      let frame;
      try {
        frame = JSON.parse(raw);
      } catch (error) {
        return; // binary TTS audio can surface here as a non-JSON string
      }
      const elapsed = Date.now() - start;

      switch (frame.type) {
        case "session_started":
          socket.send(JSON.stringify({ type: "ready" }));
          break;

        case "examiner_turn":
          if (!frame.expects_response) break;
          if (candidateTurns >= TURNS) {
            socket.send(JSON.stringify({ type: "abandon" }));
            break;
          }
          for (let offset = 0; offset < CLIP.byteLength; offset += CHUNK_BYTES) {
            socket.sendBinary(
              CLIP.slice(offset, Math.min(offset + CHUNK_BYTES, CLIP.byteLength)),
            );
          }
          socket.send(JSON.stringify({ type: "audio_end" }));
          candidateTurns++;
          break;

        case "transcript":
          if (!frame.isFinal) break;
          transcriptsReceived.add(1);
          // An empty transcript for real speech is the signature of audio being
          // decoded in the wrong format. It must not read as a fast success.
          if (!frame.text || String(frame.text).trim().length === 0) {
            emptyTranscripts.add(1);
          }
          if (!sawTranscript) {
            sawTranscript = true;
            timeToFirstTranscript.add(elapsed);
          }
          break;

        case "session_complete":
        case "evaluation":
          timeToComplete.add(elapsed);
          socket.close();
          break;

        case "error":
        case "policy_error":
          speakingErrors.add(1, { reason: String(frame.code || frame.type) });
          socket.close();
          break;
      }
    });

    socket.setTimeout(function () {
      if (!sawTranscript) speakingErrors.add(1, { reason: "no_transcript_before_timeout" });
      socket.close();
    }, 240000);
  });

  const upgraded = res && res.status === 101;
  wsUpgradeOk.add(upgraded);
  check(res, { "speaking: upgrade accepted (101)": () => upgraded });
}

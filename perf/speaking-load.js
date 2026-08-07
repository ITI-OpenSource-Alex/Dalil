// GOA-032 load test: concurrent speaking sessions through the Gateway.
//
//   docker run --rm --network goa_default \
//     -v "$PWD/perf:/perf" -e GATEWAY_WS=ws://gateway:8080 -e JWT=<token> \
//     grafana/k6 run /perf/speaking-load.js \
//     --summary-export=/perf/reports/<timestamp>.json
//
// It drives the REAL user path -- Gateway upgrade, proxy relay, Speaking
// service -- not the service's own port. A load test that skips the proxy
// measures a topology nobody runs.
//
// The metric that matters is time_to_first_criterion, NOT end-to-end. GOA-032
// changed the execution model precisely because the total cannot be brought
// under a useful number: 4 agents behind a variable-latency gateway plus CPU
// Whisper is ~77s at best. What the change buys is that the user waits ~3s
// instead of ~77s to see something, so that is what this asserts on.
import ws from "k6/ws";
import { check } from "k6";
import { Trend, Counter, Rate } from "k6/metrics";

const timeToFirstCriterion = new Trend("speaking_time_to_first_criterion_ms", true);
const timeToEvaluation = new Trend("speaking_time_to_evaluation_ms", true);
const timeToTranscript = new Trend("speaking_time_to_transcript_ms", true);
const criteriaReceived = new Counter("speaking_criteria_received");
const sessionsCompleted = new Counter("speaking_sessions_completed");
const overallBandPresent = new Rate("speaking_overall_band_present");
const sessionErrors = new Counter("speaking_session_errors");

const GATEWAY_WS = __ENV.GATEWAY_WS || "ws://localhost:8080";
const JWT = __ENV.JWT || "";
const VUS = parseInt(__ENV.VUS || "50", 10);
const AUDIO_SECONDS = parseInt(__ENV.AUDIO_SECONDS || "30", 10);

export const options = {
  scenarios: {
    speaking_sessions: {
      executor: "per-vu-iterations",
      vus: VUS,
      iterations: 1,
      maxDuration: "10m",
    },
  },
  // Thresholds are the acceptance criteria in executable form. They come from
  // the measured distribution (GOA-098 + the GOA-032 re-measure), not from
  // round numbers -- see services/speaking/internal/speaking/slo.go, which
  // must be kept in step with these.
  // These MUST match services/speaking/internal/speaking/slo.go. A load test
  // asserting a different number from the service is a load test that can pass
  // while the service breaches, or vice versa.
  thresholds: {
    "speaking_time_to_first_criterion_ms": ["p(95)<45000"],
    "speaking_time_to_evaluation_ms": ["p(95)<90000"],
    "speaking_session_errors": ["count==0"],
    "speaking_overall_band_present": ["rate>0.9"],
  },
};

// 16kHz, 16-bit, mono -- the format stt.go declares and the sidecar decodes.
const BYTES_PER_SECOND = 16000 * 2;
const CHUNK_BYTES = 16000; // ~0.5s per frame, roughly what MediaRecorder emits

// Real spoken English, loaded once in init and shared by every VU.
//
// Synthetic noise is worse than useless against the real sidecar: Whisper
// returns an empty transcript for it, so the swarm grades nothing, the run
// completes suspiciously fast, and the numbers describe a pipeline that never
// did any work. The fixture is a genuine IELTS Part 2 answer -- see
// perf/fixtures/README.md for how it is generated.
const FIXTURE = open("./fixtures/ielts-part2-answer.16k.pcm", "b");

// Sliced to AUDIO_SECONDS so the run matches the acceptance criteria's
// "30-second audio each" without needing a second fixture.
const CLIP = FIXTURE.slice(0, Math.min(AUDIO_SECONDS * BYTES_PER_SECOND, FIXTURE.byteLength));

export default function () {
  const url = `${GATEWAY_WS}/api/speaking/ws`;
  const params = JWT ? { headers: { Cookie: `access_token=${JWT}` } } : {};

  let start = 0;
  let sawFirstCriterion = false;
  let criteriaThisSession = 0;

  const res = ws.connect(url, params, function (socket) {
    socket.on("open", function () {
      start = Date.now();
      socket.send(
        JSON.stringify({
          type: "session_init",
          userId: `k6-user-${__VU}`,
          questionPrompt: "Describe a memorable journey you have taken.",
          questionType: "IELTS Part 2",
        }),
      );

      for (let offset = 0; offset < CLIP.byteLength; offset += CHUNK_BYTES) {
        socket.sendBinary(CLIP.slice(offset, Math.min(offset + CHUNK_BYTES, CLIP.byteLength)));
      }
    });

    socket.on("message", function (raw) {
      let frame;
      try {
        frame = JSON.parse(raw);
      } catch (e) {
        return; // binary TTS audio arrives here as a non-JSON string
      }
      const elapsed = Date.now() - start;

      switch (frame.type) {
        case "transcript":
          timeToTranscript.add(elapsed);
          break;
        case "criterion":
          criteriaReceived.add(1);
          criteriaThisSession++;
          if (!sawFirstCriterion) {
            sawFirstCriterion = true;
            timeToFirstCriterion.add(elapsed);
          }
          break;
        case "evaluation":
          timeToEvaluation.add(elapsed);
          // The gate from BUG-040: a band must be present only when at least 3
          // criteria completed. Recording the rate makes a regression visible
          // as a distribution shift rather than a single failed assertion.
          overallBandPresent.add(frame.overall_band !== undefined);
          check(frame, {
            "band present iff >=3 criteria completed": (f) =>
              (f.completed_count >= 3) === (f.overall_band !== undefined),
          });
          sessionsCompleted.add(1);
          socket.close();
          break;
        case "error":
          sessionErrors.add(1);
          socket.close();
          break;
      }
    });

    // Generous: the point is to measure the distribution, not to cut it off.
    socket.setTimeout(function () {
      if (criteriaThisSession === 0) {
        sessionErrors.add(1);
      }
      socket.close();
    }, 180000);
  });

  check(res, { "upgrade accepted (101)": (r) => r && r.status === 101 });
}

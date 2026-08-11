// GOA-036 — essay submission and evaluation scenario.
//
// Two hops through the Gateway, both RequirePaid:
//   POST /api/writing/essays/upload      (multipart, 5000-character cap)
//   POST /api/writing/essays/{id}/evaluate  (SSE, four criterion agents)
//
// This is the most expensive scenario per iteration -- four model calls each --
// so it is the one that governs the run's spend. The ticket's pass criterion is
// P95 < 30s; the Gateway allows this route SIX MINUTES because a single
// evaluation was measured at ~50s against AgentRouter (server.go:56-61). The
// criterion is expected to breach; the report states the measured number and
// leaves the target alone.

import { Trend, Counter } from "k6/metrics";
import { http, GATEWAY, authHeaders, classify, think, tokenFor } from "./common.js";

export const essayUploadLatency = new Trend("goa_essay_upload_duration_ms", true);
export const essayEvalLatency = new Trend("goa_essay_evaluation_duration_ms", true);
export const essayCriteria = new Trend("goa_essay_criteria_completed");
// The failure mode the 25s timeout produced: a 200 whose stream carries
// "N of 4 writing agents failed". Invisible to a status-code check.
export const essayAgentFailures = new Counter("goa_essay_agent_failures");

const ESSAY = `Some people believe that universities should focus on providing academic skills, while others argue that they should prepare students for employment. In my view, universities must do both, though the balance depends on the discipline. Academic training develops the capacity for independent reasoning that no short vocational course can replicate. A graduate who has learned to interrogate evidence, construct an argument and revise a position in the face of better data carries a transferable habit of mind that outlasts any particular technology. However, an exclusive focus on theory leaves graduates unable to convert that reasoning into practice. Employers consistently report that new hires understand principles but cannot apply them under deadline pressure, in teams, with imperfect information. The most effective universities therefore embed practical work inside academic structures rather than bolting it on. Engineering degrees requiring an industrial placement, medical training built around clinical rotations, and computer science courses assessed through substantial software projects all demonstrate that rigour and employability are not opposites. In conclusion, the dichotomy is false. Universities should teach students to think, and give them structured opportunities to act on that thinking.`;

export function essayScenario(tokens) {
  const token = tokenFor(__VU, tokens);

  // Every early-return path below goes through think() so a rejection cannot
  // turn this scenario into a retry storm.
  // Multipart, built by hand.
  //
  // k6 url-encodes a plain object body; it only produces multipart when the
  // object contains an http.file(). The Gateway's UploadEssay calls
  // c.MultipartForm() and answers 400 "invalid multipart form data" to anything
  // else -- so the first version of this scenario recorded a 2.8ms p50 upload
  // and ZERO evaluations, and the fast rejection read as excellent latency.
  // Verified against the running Gateway: url-encoded 400, multipart 200.
  const boundary = `----goa036${__VU}x${__ITER}`;
  const body =
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="essayText"\r\n\r\n${ESSAY}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="submissionType"\r\n\r\npractice\r\n` +
    `--${boundary}--\r\n`;

  const upload = http.post(`${GATEWAY}/api/writing/essays/upload`, body, {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": `multipart/form-data; boundary=${boundary}`,
    },
    timeout: "120s",
    tags: { endpoint: "essay_upload" },
  });
  essayUploadLatency.add(upload.timings.duration, { endpoint: "essay_upload" });
  if (!classify(upload, "essay_upload")) {
    think(5);
    return;
  }

  let essayId;
  try {
    essayId = upload.json("id");
  } catch (error) {
    think(5);
    return;
  }
  if (!essayId) {
    think(5);
    return;
  }

  const evaluation = http.post(
    `${GATEWAY}/api/writing/essays/${essayId}/evaluate`,
    "{}",
    {
      headers: authHeaders(token),
      // Matches the Gateway's own 6-minute ceiling for this route. A shorter
      // client timeout would record an upstream timeout wearing an upstream
      // failure's costume -- the exact confusion server.go documents.
      timeout: "360s",
      tags: { endpoint: "essay_evaluate" },
    },
  );
  essayEvalLatency.add(evaluation.timings.duration, { endpoint: "essay_evaluate" });

  if (classify(evaluation, "essay_evaluate") && evaluation.body) {
    const criteria = evaluation.body.match(/"criterion"\s*:\s*"[a-z_]+"/g);
    // Deduplicated: the stream mentions each criterion more than once.
    const unique = criteria ? new Set(criteria).size : 0;
    essayCriteria.add(unique);

    if (/agents? failed/.test(evaluation.body)) {
      essayAgentFailures.add(1);
    }
  }

  think(5);
}

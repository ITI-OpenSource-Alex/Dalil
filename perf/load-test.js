// GOA-036 — system-wide load test.
//
// Composes the four scenarios in perf/scenarios/ and runs them concurrently
// against the Gateway, which is the only entry point permitted: results from the
// direct :8082 / :8084 service paths do not measure JWT validation, rate
// limiting, correlation IDs or the WebSocket proxy, and the ticket says so
// explicitly.
//
// ---------------------------------------------------------------------------
// Concurrency, and why it is not the ticket's number
// ---------------------------------------------------------------------------
// The ticket specifies 100 chat + 20 speaking + 10 essay + 50 match, sustained
// for 10 minutes, and its own ROUTER IMPACT note then rescopes that:
//
//   "Rescope by spend, not by capability: pick a run size costing ~$5-10,
//    document the observed P95 per endpoint, and state that concurrency was
//    bounded by project budget rather than by the system."
//
// So the shape is preserved and the magnitude is scaled by LOAD_SCALE, with one
// exception: `match` makes no LLM call, so it runs at the ticket's full 50 VUs
// regardless of scale. Which bound was actually binding -- spend or catalogue
// size -- is recorded by run-load-test.sh and stated in the report.
//
// Every VU carries its own JWT. The Gateway limits /api to 60 requests per user
// per minute, so a shared token would measure the limiter rather than the
// system.

import { loadTokens } from "./scenarios/common.js";
import { chatScenario } from "./scenarios/chat.js";
import { matchScenario } from "./scenarios/match.js";
import { essayScenario } from "./scenarios/essay.js";
import { speakingScenario } from "./scenarios/speaking.js";

const TOKENS = loadTokens();

const SCALE = parseFloat(__ENV.LOAD_SCALE || "0.1");
const DURATION = __ENV.LOAD_DURATION || "10m";

// Never below 1: a scale that rounds a scenario to zero VUs silently drops it
// from the run, and the report would present three scenarios as four.
const scaled = (specified) => Math.max(1, Math.round(specified * SCALE));

export const options = {
  scenarios: {
    chat: {
      executor: "constant-vus",
      vus: scaled(100),
      duration: DURATION,
      exec: "chat",
      tags: { scenario: "chat" },
    },
    speaking: {
      executor: "constant-vus",
      vus: scaled(20),
      duration: DURATION,
      exec: "speaking",
      tags: { scenario: "speaking" },
    },
    essay: {
      executor: "constant-vus",
      vus: scaled(10),
      duration: DURATION,
      exec: "essay",
      tags: { scenario: "essay" },
    },
    // Full specified concurrency: no LLM call on this path, so it costs
    // nothing to run wide, and it is the scenario most likely to expose a
    // fan-out problem against the real catalogue.
    match: {
      executor: "constant-vus",
      vus: 50,
      duration: DURATION,
      exec: "match",
      tags: { scenario: "match" },
    },
  },

  // ------------------------------------------------------------------------
  // Thresholds are the acceptance criteria in executable form.
  //
  // Two of the ticket's four are known-unreachable on this stack and are left
  // at the ticket's value ON PURPOSE, so the run reports them as breached with
  // a measured number rather than passing against a widened target. GOA-032 set
  // the precedent when a capacity-bound run failed: "the test demanded the lie".
  //
  //   chat P95 < 5s      measured 34s (101s before the ANN recall fix)
  //   essay P95 < 30s    measured ~52s; the Gateway allows the route 6 minutes
  //                      precisely because ~50s is normal
  //
  // abortOnFail is false everywhere: a breach must not end the run, because the
  // run is the evidence.
  // ------------------------------------------------------------------------
  thresholds: {
    "goa_chat_duration_ms": ["p(95)<5000"],
    "goa_essay_evaluation_duration_ms": ["p(95)<30000"],
    // Speaking's own SLO, not the ticket's "P95 < 3s" -- that number does not
    // name a quantity this system produces. slo.go's measured budget is
    // time-to-first-criterion p95 < 45s against a measured 28.7s; the closest
    // v3 analogue is time to first transcript, which is STT-bound.
    "goa_speaking_time_to_first_transcript_ms": ["p(95)<45000"],
    "goa_speaking_ws_upgrade_success": ["rate>0.99"],
    "goa_speaking_empty_transcripts": ["count==0"],
    "goa_match_duration_ms": ["p(95)<5000"],
    // The ticket's "error rate < 1%". 5xx and transport failures only --
    // 429s and 425s are counted separately and deliberately excluded, because
    // they are the Gateway and the replication contract behaving correctly.
    "goa_server_errors": ["count<10"],
    "goa_essay_agent_failures": ["count==0"],
  },
};

export function chat() {
  chatScenario(TOKENS);
}
export function match() {
  matchScenario(TOKENS);
}
export function essay() {
  essayScenario(TOKENS);
}
export function speaking() {
  speakingScenario(TOKENS);
}

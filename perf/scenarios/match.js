// GOA-036 — profile / opportunity-match scenario.
//
// POST /api/opportunities/query through the Gateway. The Gateway CONSTRUCTS the
// upstream body from the validated token rather than forwarding the client's,
// so this measures the real route rather than an artificial one.
//
// This is the scenario the ticket's Option B warning is about:
//
//   "Load-testing /match against ~100 programs proves nothing about production;
//    against the full ~20,000-program catalog it becomes the test that finds
//    fan-out problems."
//
// So the catalogue size at run time is part of the result, not context for it.
// run-load-test.sh records it and the report states which bound was binding.
//
// The /match batch rewrite has landed (one candidate query, in-memory scoring,
// top-10 limit), which is why this scenario can run at the ticket's full
// specified concurrency: unlike chat and essay it makes no LLM call, so it costs
// nothing to run wide.

import { Trend, Counter } from "k6/metrics";
import { http, GATEWAY, authHeaders, classify, think, tokenFor } from "./common.js";

export const matchLatency = new Trend("goa_match_duration_ms", true);
export const matchProgramCount = new Trend("goa_match_program_count");
// 425 is a documented contract, not an error: the profile replicates to RAG
// over SQS and /match answers "Profile not yet replicated. Please retry."
// until it lands. Counted on its own so it can never inflate the error rate.
export const notReplicated = new Counter("goa_match_not_replicated");

export function matchScenario(tokens) {
  const token = tokenFor(__VU, tokens);

  const response = http.post(`${GATEWAY}/api/opportunities/query`, "{}", {
    headers: authHeaders(token),
    timeout: "120s",
    tags: { endpoint: "match" },
  });

  matchLatency.add(response.timings.duration, { endpoint: "match" });

  if (response.status === 425) {
    notReplicated.add(1);
    think(10);
    return;
  }

  if (classify(response, "match")) {
    try {
      const programs = response.json("programs");
      matchProgramCount.add(programs ? programs.length : 0);
    } catch (error) {
      // A 200 whose body will not parse is a real defect; leave it to the
      // check in classify() rather than swallowing it as a zero.
    }
  }
  // A person opening their opportunities page does it occasionally, not in a
  // loop. At 10s this VU makes ~6 requests a minute, comfortably inside the
  // Gateway's 60/min per-user budget.
  think(10);
}

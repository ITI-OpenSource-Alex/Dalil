// GOA-036 — chat (RAG) scenario.
//
// POST /api/chat through the Gateway: JWT check, 2000-character validation, the
// hourly AI limiter, then orchestration -> RAG retrieval -> a real model call,
// streamed back as SSE.
//
// The ticket's pass criterion is P95 < 5s. Measured on this stack a single
// uncached query took 101s before the ANN recall fix and 34s after it, so this
// scenario is expected to breach and the report says so with the number rather
// than widening the threshold. GOA-032 set that precedent when it refused to
// relax an SLO for a capacity-bound run: "the test demanded the lie".

import { Trend } from "k6/metrics";
import { http, GATEWAY, authHeaders, classify, think, tokenFor } from "./common.js";

export const chatLatency = new Trend("goa_chat_duration_ms", true);
export const chatSources = new Trend("goa_chat_source_count");

// A spread rather than one question, so the RAG cache cannot turn the whole
// scenario into a measurement of Redis. Mixed visa and programme intents,
// because they retrieve from different corpora with very different sizes.
const QUESTIONS = [
  "What are the student visa requirements for Germany?",
  "Which universities in Germany offer a master's in software engineering?",
  "How much money do I need in a blocked account for a German student visa?",
  "What IELTS score do I need for a master's in the Netherlands?",
  "Tell me about student residence permits in Austria.",
  "Which Italian universities teach computer science in English?",
  "What documents does a French student visa application need?",
  "Are there scholarships for Egyptian students in Europe?",
];

export function chatScenario(tokens) {
  const token = tokenFor(__VU, tokens);
  const question = QUESTIONS[(__VU + __ITER) % QUESTIONS.length];

  const response = http.post(
    `${GATEWAY}/api/chat`,
    JSON.stringify({
      message: question,
      sessionId: `k6-chat-${__VU}-${__ITER}`,
    }),
    {
      headers: authHeaders(token),
      // Above the Gateway's own 5-minute streaming ceiling would measure k6's
      // patience instead of the system's; below it would report the system as
      // failing when it was still working.
      timeout: "300s",
      tags: { endpoint: "chat" },
    },
  );

  chatLatency.add(response.timings.duration, { endpoint: "chat" });

  if (classify(response, "chat")) {
    // Counting citations is the cheapest available check that retrieval did
    // something. A 200 with zero sources is the shape of the ANN recall defect
    // this work found, and it would otherwise look like a fast success.
    const matches = response.body ? response.body.match(/"source_url"/g) : null;
    chatSources.add(matches ? matches.length : 0);
  }

  // The request itself takes tens of seconds, so this is mostly about not
  // re-firing the instant a failure returns quickly.
  think(5);
}

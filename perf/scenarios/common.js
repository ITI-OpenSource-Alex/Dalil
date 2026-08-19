// GOA-036 — shared helpers for the system-wide load test.
//
// Everything here exists to keep the scenarios measuring the SYSTEM rather than
// measuring the Gateway's own defences. Two of those defences bite immediately:
//
//   * /api is rate-limited to 60 requests per user per minute. One JWT shared
//     across 100 VUs measures that limiter and nothing else.
//   * Each AI route has its own hourly ceiling (chat, essay evaluation, CV
//     review, opportunity search), also per user.
//
// So every VU carries its own identity. The tokens are minted before the run by
// perf/run-load-test.sh and handed in as JSON, because minting them inside k6
// would put user registration on the measured path.

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

export const GATEWAY = __ENV.GATEWAY || "http://localhost:8080";

// Counted separately from generic failures. A 429 means the limiter fired,
// which is a fact about the test's shape rather than about the system's
// capacity, and collapsing the two produces an "error rate" that cannot be
// acted on.
export const rateLimited = new Counter("goa_rate_limited");
export const serverErrors = new Counter("goa_server_errors");
// Separated from both of the above: an auth or entitlement rejection is a fault
// in the run's SETUP, not in the system's capacity, and burying it in either
// bucket produces a number nobody can act on.
export const authFailures = new Counter("goa_auth_failures");

/**
 * Per-VU identity.
 *
 * Tokens are loaded once in init (k6 shares init-scope data across VUs) and
 * indexed by VU number, wrapping if the pool is smaller than the VU count --
 * wrapping reintroduces sharing, so run-load-test.sh mints at least as many
 * tokens as the largest scenario needs and the report records the pool size.
 */
export function tokenFor(vu, tokens) {
  return tokens[(vu - 1) % tokens.length];
}

export function authHeaders(token, extra) {
  return Object.assign(
    {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    extra || {},
  );
}

/**
 * Classifies one response and records it.
 *
 * Returns true only for a genuine success, so a scenario can decide whether to
 * continue. A 429 is explicitly NOT a success and explicitly NOT a server
 * error: it is the limiter doing its job.
 */
export function classify(response, name) {
  if (response.status === 429) {
    rateLimited.add(1, { endpoint: name });
    return false;
  }
  // 401/403 are not capacity problems and must not sit in the same bucket as a
  // 5xx. On this stack they mean the token expired mid-run (1h TTL) or the
  // account is not paid -- both setup faults, and both would otherwise be
  // reported as the system failing under load.
  if (response.status === 401 || response.status === 403) {
    authFailures.add(1, { endpoint: name, status: String(response.status) });
    return false;
  }
  if (response.status >= 500 || response.status === 0) {
    serverErrors.add(1, { endpoint: name, status: String(response.status) });
    return false;
  }
  return check(response, {
    [`${name}: 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
}

/**
 * Think time between iterations.
 *
 * Not padding -- without it `constant-vus` is a busy loop, and a busy loop
 * against a rate-limited API measures the rate limiter. The first run of this
 * harness did exactly that: 144,292 requests in 45 seconds, of which 144,270
 * were 429s, and the resulting "match p95 = 34ms" was the latency of being
 * refused.
 *
 * A concurrent USER is not a concurrent REQUEST. The Gateway allows 60 requests
 * per user per minute, so a VU representing one person has to pause like one.
 * The defaults below keep each VU under that ceiling with room to spare, and
 * jitter stops fifty VUs marching in lockstep into the same second.
 */
export function think(seconds) {
  const base = parseFloat(__ENV.THINK_TIME || String(seconds));
  // +/-20% jitter.
  const jittered = base * (0.8 + Math.random() * 0.4);
  sleep(jittered);
}

export function loadTokens() {
  // Written by run-load-test.sh. Deliberately fails loudly: a missing file
  // silently producing an empty pool would make every VU anonymous and every
  // request a 401, which reads as a catastrophic error rate.
  const raw = open(__ENV.TOKENS_FILE || "./tokens.json");
  const tokens = JSON.parse(raw);
  if (!Array.isArray(tokens) || tokens.length === 0) {
    throw new Error("tokens.json is empty; run perf/run-load-test.sh, not k6 directly");
  }
  return tokens;
}

export { http };

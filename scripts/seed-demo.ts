#!/usr/bin/env node
/* GOA-047: idempotent demo reset and preflight through owning service APIs. */

const fs = require("node:fs");
const path = require("node:path");

const snapshotPath = path.join(__dirname, "demo-snapshot.json");
// The live MastersPortal catalog advertises ~20k Engineering/CS results before
// Europe filtering and cross-discipline deduplication. Its measured in-scope
// measured demo corpus on 2026-08-12 was 7,925 university documents (8,001 total).
const DEMO_CORPUS_MINIMUM = 7_500;

function loadSnapshot() {
  return JSON.parse(fs.readFileSync(snapshotPath, "utf8"));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function validateSnapshot(snapshot) {
  assert(snapshot.schema_version === "goa-demo-snapshot/v1", "unsupported snapshot schema");
  assert(snapshot.demo_user?.display_name === "Ahmed", "demo user must be Ahmed");
  assert(snapshot.demo_user?.profile?.ects === 180, "Ahmed must have 180 ECTS");
  assert(snapshot.demo_user?.profile?.ieltsScore === 6.5, "Ahmed must have IELTS 6.5");
  assert(snapshot.demo_user?.profile?.fieldOfStudy === "Electrical Engineering", "Ahmed must have an electrical-engineering background");
  const tiers = snapshot.programs.map((program) => program.tier).sort();
  assert(JSON.stringify(tiers) === JSON.stringify(["blocked", "high", "low", "mid", "mid"]), "snapshot must contain 1 blocked, 1 low, 2 mid and 1 high match");
  for (const program of snapshot.programs) {
    assert(/^https:\/\//.test(program.source_url), `${program.program_name}: source_url must be HTTPS`);
    assert(/^[a-f0-9]{64}$/.test(program.content_hash), `${program.program_name}: content_hash missing`);
    assert(Boolean(Date.parse(program.last_scraped_at)), `${program.program_name}: last_scraped_at missing`);
  }
  assert(/^https:\/\//.test(snapshot.visa.source_url), "visa source_url must be HTTPS");
  assert(Object.keys(snapshot.visa.extraction_evidence || {}).length > 0, "visa extraction evidence missing");
  assert(Boolean(Date.parse(snapshot.visa.last_verified_at)), "visa last_verified_at missing");
  return snapshot;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) {
    const error = new Error(`${options.method || "GET"} ${url} -> ${response.status}: ${text}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

function jsonOptions(method, body, headers = {}) {
  return {
    method,
    headers: { "content-type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function decodeSubject(accessToken) {
  const payload = JSON.parse(Buffer.from(accessToken.split(".")[1], "base64url").toString("utf8"));
  assert(payload.sub, "gateway access token has no subject");
  return payload.sub;
}

async function ensureAccount(snapshot, gateway, password) {
  try {
    await requestJson(`${gateway}/users`, jsonOptions("POST", {
      email: snapshot.demo_user.email,
      password,
    }));
  } catch (error) {
    if (error.status !== 409) throw error;
  }
  const login = await requestJson(`${gateway}/auth/login`, jsonOptions("POST", {
    email: snapshot.demo_user.email,
    password,
  }));
  return { token: login.access_token, userId: decodeSubject(login.access_token) };
}

async function ensurePaidDemoAccess(gateway, token) {
  const headers = { authorization: `Bearer ${token}` };
  const current = await requestJson(`${gateway}/api/profile`, { headers });
  if (current.subscriptionTier === "paid") return;

  const checkout = await requestJson(
    `${gateway}/api/billing/create-checkout`,
    jsonOptions("POST", {
      successUrl: "http://localhost:3000/billing/success",
      cancelUrl: "http://localhost:3000/pricing?checkout=cancelled",
    }, headers),
  );
  const checkoutToken = new URL(checkout.url).searchParams.get("session");
  assert(checkoutToken, "demo checkout did not return a session token");
  const result = await requestJson(
    `${gateway}/api/billing/demo/confirm`,
    jsonOptions("POST", {
      token: checkoutToken,
      cardNumber: "4242424242424242",
    }, headers),
  );
  assert(result.status === "succeeded", `demo subscription setup ${result.status}`);

  const refreshed = await requestJson(`${gateway}/api/profile`, { headers });
  assert(refreshed.subscriptionTier === "paid", "paid demo access was not persisted");
}

async function restoreOwnedSnapshots(snapshot, rag, internalKey) {
  const headers = { "X-Internal-API-Key": internalKey };
  for (const program of snapshot.programs) {
    const { tier, programId, last_scraped_at, ...payload } = program;
    await requestJson(`${rag}/internal/program-requirements`, jsonOptions("POST", payload, headers));
  }
  const { last_verified_at, ...visa } = snapshot.visa;
  await requestJson(`${rag}/internal/visa-requirements`, jsonOptions("POST", visa, headers));
}

function actualTier(program) {
  if (program.result?.blocked_by) return "blocked";
  const score = Number(program.result?.score);
  if (score >= 90) return "high";
  if (score >= 75) return "mid";
  return "low";
}

async function pollMatches(gateway, token) {
  const deadline = Date.now() + 30_000;
  let lastError;
  // A profile update reaches RAG asynchronously through SQS. Give the consumer
  // one delivery window before querying; 425 readiness responses are still real
  // Gateway requests and therefore consume the hourly opportunity allowance.
  await new Promise((resolve) => setTimeout(resolve, 2_000));
  while (Date.now() < deadline) {
    try {
      const response = await requestJson(
        `${gateway}/api/opportunities/query`,
        jsonOptions("POST", {}, { authorization: `Bearer ${token}` }),
      );
      if (response.programs.length > 0) return response.programs;
      lastError = new Error("ranked opportunity response is empty");
    } catch (error) {
      if (error.status !== 425) throw error;
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw lastError;
}

async function resetDemo(config = {}) {
  const started = Date.now();
  const snapshot = validateSnapshot(loadSnapshot());
  const gateway = config.gateway || process.env.DEMO_GATEWAY_URL || "http://gateway:8080";
  const rag = config.rag || process.env.DEMO_RAG_URL || "http://rag:8084";
  const exam = config.exam || process.env.DEMO_EXAM_URL || "http://exam:8085";
  const internalKey = config.internalKey || process.env.INTERNAL_API_KEY || "supersecret_internal_key_123";
  const password = config.password || process.env.DEMO_USER_PASSWORD;
  assert(password && password.length >= 6, "DEMO_USER_PASSWORD (minimum 6 characters) is required");

  await restoreOwnedSnapshots(snapshot, rag, internalKey);
  const account = await ensureAccount(snapshot, gateway, password);
  await ensurePaidDemoAccess(gateway, account.token);
  await requestJson(
    `${gateway}/internal/demo/users/${account.userId}/quotas/reset`,
    jsonOptions("POST", undefined, { "X-Internal-API-Key": internalKey }),
  );
  await requestJson(
    `${gateway}/api/profile`,
    jsonOptions("PUT", snapshot.demo_user.profile, { authorization: `Bearer ${account.token}` }),
  );
  await requestJson(
    `${exam}/internal/demo/users/${account.userId}/reading-history/reset`,
    jsonOptions("POST", undefined, { "X-Internal-API-Key": internalKey }),
  );
  const report = await preflight({ snapshot, gateway, rag, internalKey, account });
  report.reset_duration_ms = Date.now() - started;
  assert(report.reset_duration_ms < 30_000, `reset took ${report.reset_duration_ms}ms (limit 30000ms)`);
  return report;
}

async function preflight({ snapshot, gateway, rag, internalKey, account }) {
  const corpus = await requestJson(`${rag}/internal/documents/stats`, {
    headers: { "X-Internal-API-Key": internalKey },
  });
  assert(
    corpus.total >= DEMO_CORPUS_MINIMUM,
    `RAG corpus has ${corpus.total} documents; demo requires at least ${DEMO_CORPUS_MINIMUM}`,
  );
  assert(Boolean(Date.parse(corpus.last_updated_at)), "RAG corpus has no successful update timestamp");
  await pollMatches(gateway, account.token);
  const authHeaders = { authorization: `Bearer ${account.token}` };
  const details = await Promise.all(snapshot.programs.map((expected) =>
    requestJson(`${gateway}/api/opportunities/${expected.programId}`, { headers: authHeaders })
  ));
  const selected = snapshot.programs.map((expected, index) => {
    const actual = details[index];
    assert(actual.sourceUrl === expected.source_url, `${expected.program_name}: source metadata changed`);
    assert(Boolean(Date.parse(actual.lastScrapedAt)), `${expected.program_name}: successful ingestion timestamp missing`);
    const tier = actualTier(actual);
    assert(tier === expected.tier, `${expected.program_name}: expected ${expected.tier}, got ${tier} (${actual.result.score})`);
    return { programId: actual.programId, programName: actual.programName, tier, score: actual.result.score, sourceUrl: actual.sourceUrl, lastScrapedAt: actual.lastScrapedAt };
  });
  const visa = await requestJson(
    `${rag}/internal/visa-requirements?source_url=${encodeURIComponent(snapshot.visa.source_url)}`,
    { headers: { "X-Internal-API-Key": internalKey } },
  );
  assert(visa.source_url === snapshot.visa.source_url, "persisted visa source URL missing");
  assert(Object.keys(visa.extraction_evidence || {}).length > 0, "persisted visa extraction evidence missing");
  assert(Boolean(Date.parse(visa.last_verified_at)), "persisted visa verification timestamp missing");

  const highMatch = selected.find((program) => program.tier === "high");
  assert(highMatch, "no high-tier programme available for checklist preflight");
  let checklist = await requestJson(
    `${gateway}/api/checklists/${highMatch.programId}`,
    { headers: authHeaders },
  );
  assert(checklist.generatedBy === "requirements", "checklist is not fact-derived");
  assert(checklist.items.length > 0, "checklist has no source-derived items");
  for (const item of checklist.items) {
    await requestJson(
      `${gateway}/api/checklists/${highMatch.programId}/items/${encodeURIComponent(item.itemId)}`,
      jsonOptions("PUT", { checked: false }, authHeaders),
    );
  }
  checklist = await requestJson(
    `${gateway}/api/checklists/${highMatch.programId}`,
    { headers: authHeaders },
  );
  assert(checklist.items.every((item) => item.checked === false), "checklist reset did not persist");

  const financial = await requestJson(
    `${gateway}/api/checklists/${highMatch.programId}/financial`,
    { headers: authHeaders },
  );
  assert(financial.items.length > 0, "Germany financial guidance is missing");
  const officialFinancial = financial.items.find(
    (item) => item.sourceUrl === snapshot.visa.source_url,
  );
  assert(officialFinancial, "financial guidance does not include the frozen official visa source");
  assert(
    financial.items.every((item) => Boolean(Date.parse(item.lastVerifiedAt))),
    "financial guidance lacks a verification timestamp",
  );
  const history = await requestJson(`${gateway}/api/exam/history`, {
    headers: authHeaders,
  });
  const bands = history
    .filter((row) => row.skill === "reading")
    .slice(0, 3)
    .map((row) => Number(row.bandScore))
    .reverse();
  assert(JSON.stringify(bands) === JSON.stringify([5.5, 6, 6.5]), `Reading history order is ${JSON.stringify(bands)}, expected [5.5,6,6.5]`);
  // Leave the user with a fresh demo allowance after preflight itself exercised
  // the metered route.
  await requestJson(
    `${gateway}/internal/demo/users/${account.userId}/quotas/reset`,
    jsonOptions("POST", undefined, { "X-Internal-API-Key": internalKey }),
  );
  return {
    status: "ready",
    user_id: account.userId,
    email: snapshot.demo_user.email,
    corpus,
    selected_programs: selected,
    visa_source: visa.source_url,
    visa_last_verified_at: visa.last_verified_at,
    checklist: {
      program_id: highMatch.programId,
      generated_by: checklist.generatedBy,
      item_count: checklist.items.length,
      all_items_reset: true,
      financial_item_count: financial.items.length,
      financial_source: officialFinancial.sourceUrl,
      financial_message: officialFinancial.message,
    },
    reading_bands_oldest_to_newest: bands,
  };
}

async function main() {
  const command = process.argv[2] || "reset";
  if (!new Set(["reset", "check"]).has(command)) throw new Error("usage: seed-demo.ts [reset|check]");
  const snapshot = validateSnapshot(loadSnapshot());
  const gateway = process.env.DEMO_GATEWAY_URL || "http://gateway:8080";
  const rag = process.env.DEMO_RAG_URL || "http://rag:8084";
  const internalKey = process.env.INTERNAL_API_KEY || "supersecret_internal_key_123";
  const password = process.env.DEMO_USER_PASSWORD;
  assert(password && password.length >= 6, "DEMO_USER_PASSWORD (minimum 6 characters) is required");
  const report = command === "reset"
    ? await resetDemo({ gateway, rag, internalKey, password })
    : await (async () => {
        const account = await ensureAccount(snapshot, gateway, password);
        return preflight({ snapshot, gateway, rag, internalKey, account });
      })();
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

module.exports = {
  actualTier,
  ensurePaidDemoAccess,
  loadSnapshot,
  preflight,
  resetDemo,
  validateSnapshot,
};
if (require.main === module) main().catch((error) => { console.error(`DEMO NOT READY: ${error.message}`); process.exitCode = 1; });

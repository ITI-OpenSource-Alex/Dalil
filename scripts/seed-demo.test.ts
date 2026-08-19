const test = require("node:test");
const assert = require("node:assert/strict");
const { actualTier, loadSnapshot, validateSnapshot } = require("./seed-demo.ts");

test("frozen snapshot carries exact source provenance and tier distribution", () => {
  const snapshot = validateSnapshot(loadSnapshot());
  assert.deepEqual(
    snapshot.programs.map((program) => program.tier).sort(),
    ["blocked", "high", "low", "mid", "mid"],
  );
  assert.ok(snapshot.programs.every((program) => program.source_url.startsWith("https://www.mastersportal.com/")));
  assert.ok(snapshot.visa.source_url.startsWith("https://home-affairs.ec.europa.eu/"));
});

test("live score buckets are deterministic and blocked takes precedence", () => {
  assert.equal(actualTier({ result: { score: 99, blocked_by: null } }), "high");
  assert.equal(actualTier({ result: { score: 85, blocked_by: null } }), "mid");
  assert.equal(actualTier({ result: { score: 72.75, blocked_by: null } }), "low");
  assert.equal(actualTier({ result: { score: 99, blocked_by: "ielts" } }), "blocked");
});

# Task 07: Shared `content_hash` Helper + Idempotency Semantics

## Objective
Extract the existing private content-hash computation out of `german_embassy_cairo.py` into a shared
ingestion-side helper, so the three GOA-088 adapters (Tasks 09–11) don't each re-implement it, and
document the idempotency semantics this ticket relies on end-to-end.

## Background
`services/ingestion/app/adapters/german_embassy_cairo.py:75-78` already implements exactly the hash
function this ticket needs:

```
def _compute_content_hash(record: dict) -> str:
    canonical = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

It is `sha256` over a `sort_keys=True` JSON dump of the *normalized structured record* (not raw HTML),
computed before the `content_hash` key itself is added to the record. This is GOA-088's client-side
content-hash generation strategy, unchanged by this ticket — this task only relocates the function so
it isn't duplicated three more times, and documents its role in the wider idempotency story (client
computes and attaches the hash; the RAG service's `ON CONFLICT` upsert compares it, per Tasks 05/06).

## Scope
- `services/ingestion/app/core/content_hash.py` (new)
- `services/ingestion/app/adapters/german_embassy_cairo.py` (import swap only)

No RAG-service-side code in this task (that's Tasks 05/06, already specified).

## Implementation Steps
- [ ] Create `services/ingestion/app/core/content_hash.py` with a single public function,
      `compute_content_hash(record: dict) -> str`, containing the exact same logic as
      `german_embassy_cairo.py:75-78` — same algorithm, same serialization (`sort_keys=True,
      default=str`), same encoding. This must be a pure relocation, not a reimplementation, so
      existing stored hashes for `visa_requirements` rows continue to match on the next scrape.
- [ ] Update `german_embassy_cairo.py` to import and call the shared function, removing its private
      `_compute_content_hash`.
- [ ] Confirm (via existing tests) that `GermanEmbassyCairoAdapter`'s output is byte-for-byte identical
      before and after the refactor — same hash for the same input record.
- [ ] Document (in this file, for implementers of Tasks 09–11) the exact convention: compute the hash
      over the record dict *before* `content_hash` is added as a key, so the hash never includes
      itself.

## Expected Files/Modules
- `services/ingestion/app/core/content_hash.py` (new)
- `services/ingestion/app/adapters/german_embassy_cairo.py` (edited — import only, no logic change)

## Dependencies
None — this is independent of the RAG-service tasks and can be done in parallel with Tasks 01–06.

## Risks
- **Algorithm drift breaks existing idempotency.** If the relocated function's serialization differs
  even slightly from the original (e.g. different `json.dumps` kwargs, different encoding), every
  `visa_requirements` row will appear to have "changed" on the next ingestion run after this refactor
  ships, causing spurious `last_scraped_at`/field churn for GOA-086's data. The relocation must be
  copy-exact, verified by a regression test asserting identical hash output for a fixed input before
  and after the move.
- **Scope creep temptation.** This task should not change the hashing algorithm, add versioning, or
  "improve" the hash strategy (e.g. excluding certain fields) — GOA-088 explicitly retains GOA-088's
  (and GOA-086's) existing client-side content-hash generation strategy unchanged; any perceived
  improvement belongs under Future Improvements in the master plan, not folded in here.

## Definition of Done
- `compute_content_hash()` exists in `app/core/content_hash.py` and is used by
  `GermanEmbassyCairoAdapter`.
- `german_embassy_cairo.py`'s existing tests pass unmodified.
- A new unit test in this task's own test file confirms: same input dict → same hash (determinism);
  changing any field's value → different hash (sensitivity); the function is dict-key-order-independent
  (relies on `sort_keys=True`).

## Acceptance Criteria
- No behavior change to any existing GOA-086 adapter or test.
- The shared helper is ready for direct reuse by Tasks 09, 10, and 11 without further modification.

## Notes for Implementation
- This task deliberately does not touch Tasks 05/06's server-side comparison logic
  (`content_hash IS DISTINCT FROM EXCLUDED.content_hash`, or the always-rewrite equivalent decided in
  those tasks) — this task is only about how the hash is *computed* on the ingestion side, not how
  it's *compared* on the RAG-service side.
- Tasks 09, 10, and 11 should each call `compute_content_hash(record)` on their fully-built structured
  record dict (before attaching `content_hash` as a key on that same dict), exactly matching
  `german_embassy_cairo.py:168-188`'s `_build_record()` pattern.

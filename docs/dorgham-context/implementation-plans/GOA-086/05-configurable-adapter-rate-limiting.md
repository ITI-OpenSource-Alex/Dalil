# Task 05: Configurable Rate Limiting on Base Adapter Classes

## Goal
Add optional `min_delay`/`max_delay` constructor parameters to `BaseAdapter` and
`BasePlaywrightAdapter`, defaulting to today's values (1.0/2.0 seconds), so new adapters can request
the ticket-required 2–3 second delay without changing the 6 existing adapters' behavior.

## Why this task exists
`services/ingestion/app/core/rate_limiter.py::polite_delay(min_seconds=1.0, max_seconds=2.0)` is
already parameterized, but both base adapter classes' `scrape()` template methods currently call it
with no arguments (hardcoded to the 1.0–2.0s default). GOA-086 requires 2–3s delays between requests
for its 9 adapters. This is a small, isolated, backward-compatible change that must land before any
of the 9 adapter tasks, since those adapters' constructors will pass the new parameters.

## Prerequisites
- None.

## Scope
Only `services/ingestion/app/adapters/base_adapter.py` and
`services/ingestion/app/adapters/base_playwright_adapter.py`.

## Implementation Steps
- [ ] In `BaseAdapter.__init__`, add `min_delay: float = 1.0, max_delay: float = 2.0` parameters;
      store as `self.min_delay` / `self.max_delay`.
- [ ] In `BaseAdapter.scrape()`, replace both bare `await polite_delay()` calls with
      `await polite_delay(self.min_delay, self.max_delay)`.
- [ ] Repeat identically for `BasePlaywrightAdapter.__init__` and its `scrape()`'s
      `await polite_delay()` call.
- [ ] Do not change any other behavior of either template method (robots.txt check, crawl loop,
      exception handling, return shape all stay exactly as they are).

## Files Expected to Change
- `services/ingestion/app/adapters/base_adapter.py`
- `services/ingestion/app/adapters/base_playwright_adapter.py`

## Acceptance Criteria
- Instantiating any existing adapter (e.g. `DAADAdapter()`, `IELTSOrgAdapter()`) with no new
  arguments behaves identically to before — delays still sampled from the 1.0–2.0s range.
- An adapter constructed with `min_delay=2.0, max_delay=3.0` samples delays from that range instead.

## Testing
- **Regression (primary signal)**: run the existing `services/ingestion/tests/test_adapters.py`
  suite unmodified and confirm 100% pass — this is the key check that the change is truly
  behavior-neutral for existing adapters.
- New focused unit test: mock `polite_delay` and assert it's called with `(1.0, 2.0)` for an adapter
  built with defaults, and with `(2.0, 3.0)` for one built with the override — assert on call
  arguments, not real elapsed time, to keep the test fast and deterministic.

## Notes
- All 9 adapter tasks (Tasks 07–15) depend on this task. Do not start writing the Egypt adapters
  until this lands, since their constructors will pass `min_delay=2.0, max_delay=3.0`.
- This task does not touch `extract_documents()`, `scrape()`'s return type, or anything related to
  the additive `visa_requirements` key described in the adapter tasks — that's a separate, unrelated
  concern handled per-adapter.

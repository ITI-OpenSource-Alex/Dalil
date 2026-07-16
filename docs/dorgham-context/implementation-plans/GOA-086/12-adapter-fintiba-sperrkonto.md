# Task 12: `FintibaSperrkontoAdapter`

## Goal
Implement `FintibaSperrkontoAdapter`, scraping blocked-account (Sperrkonto) requirements from
Fintiba, producing both RAG document chunks and structured `visa_requirements` record(s) focused on
the `proof_of_funds` payload.

## Why this task exists
GOA-086 explicitly names this adapter and its Egypt-specific context list includes "Blocked account
(Sperrkonto)" and "Proof of funds in EGP context" directly. This is the primary source for the
ticket's Definition-of-Done integration check "verify a blocked account query," and is one of the 7
adapters the ticket requires a unit test for. It's also, per the ticket's implementation notes, one
of only two adapters required to use Playwright.

## Prerequisites
- Task 05 (configurable `min_delay`/`max_delay` on `BasePlaywrightAdapter`).
- **Open item**: exact target URL for Fintiba's Sperrkonto requirements page needs confirmation (see
  main plan, Question #2). Fixture-based development can proceed regardless.
- **Judgment call to resolve during implementation**: Fintiba is a blocked-account *provider*, not a
  visa-issuing body — recommend `country="Germany"` (Sperrkonto is a German student-visa financial
  requirement), `issuing_body="Fintiba GmbH"`, `visa_type` something like
  `"Student Visa (Blocked Account Requirement)"`, with the primary payload living in
  `proof_of_funds` (`amount_eur`, `blocked_account_providers=["Fintiba"]`,
  `minimum_balance_period_days`, `sponsor_letter_accepted`, `notes_egypt`). Cross-check this doesn't
  collide with Task 07's (German Embassy Cairo) or Task 08's (APS Cairo) `visa_type` keys for the
  same `country`.

## Scope
One new adapter file: `services/ingestion/app/adapters/fintiba_sperrkonto.py`, plus its unit
test(s). Uses `BasePlaywrightAdapter`.

## Implementation Steps
- [ ] Subclass `BasePlaywrightAdapter`.
- [ ] Constructor: `source_name="fintiba_sperrkonto"`, `category="visa"`, `country="Germany"`,
      `min_delay=2.0, max_delay=3.0`, appropriate `wait_selector`.
- [ ] Implement `extract_documents(html, url)` returning standard chunk-shaped dict(s), with the
      `"visa_requirements"` key populated per the judgment call above — prioritize extracting
      `proof_of_funds.amount_eur` and `minimum_balance_period_days` accurately, since this is the
      field the ticket's "blocked account query" integration check depends on.
- [ ] Set `egyptian_specific=True` (Fintiba explicitly serves the Egypt-context requirement per the
      ticket).
- [ ] Implement Arabic-page skip (likely a no-op if Fintiba has no Arabic version — implement the
      check anyway for consistency, it should simply never trigger).
- [ ] Use inherited `fetch_page` (Playwright, backoff-wrapped).

## Files Expected to Change
- `services/ingestion/app/adapters/fintiba_sperrkonto.py` (new)
- `services/ingestion/tests/test_egypt_adapters.py` (new or appended)

## Acceptance Criteria
- `scrape()` returns correctly structured document dict(s) with `category="visa"`,
  `country="Germany"`.
- At least one dict includes populated `visa_requirements` with a meaningfully complete
  `proof_of_funds` object (not all fields `None`).
- Content is specific enough that Task 18's "verify a blocked account query" integration check can
  be meaningfully answered from the resulting document chunks.

## Testing
- Unit test (ticket explicitly requires this adapter's unit test): happy path with a fixture
  containing realistic Sperrkonto figures; partial-data robustness (fixture missing
  `sponsor_letter_accepted` info, etc. — must not crash); Arabic-skip (should be a no-op pass-through
  in practice, but the code path must exist and be exercised).

## Notes
- This is one of only 2 Playwright-based adapters (with Task 11); expect it to need periodic
  maintenance if Fintiba's site structure changes.
- Must be added to both ingestion entry points in Task 16.

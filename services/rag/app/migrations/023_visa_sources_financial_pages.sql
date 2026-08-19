-- GOA-109 (re-scoped): point visa sources at pages that PUBLISH THE AMOUNTS, and
-- deactivate sources whose URLs are dead.
--
-- Why this matters more than any other visa field: proof-of-funds is the requirement
-- Egyptian applicants must plan months ahead for. A source that documents "you must
-- show enough money" without a figure is not actionable.
--
-- Verified live 2026-07-25:
--   gov.uk/student-visa        -> prose only, "the amount will vary" (amounts: [])
--   gov.uk/student-visa/money  -> GBP 1,529 / 1,171 / 558 per month, London-qualified
-- The extraction of the landing page counted as a SUCCESS while storing an empty
-- amounts array, which then rendered a contentless financial gap item.
--
-- Also note those figures were GBP 1,334 / 1,023 earlier in this project's history:
-- published amounts change, which is exactly why they are extracted from the live page
-- with verbatim evidence rather than recalled by a model.

UPDATE visa_sources
SET source_url = 'https://www.gov.uk/student-visa/money'
WHERE country = 'United Kingdom'
  AND source_url = 'https://www.gov.uk/student-visa';

-- These four fetch 404 with both the ingestion bot UA and a browser UA; the embassies
-- have reorganised their sites. Deactivated so runs stop spending fetches and the
-- telemetry stops reporting permanent failures. Re-activate as each replacement URL is
-- found AND confirmed to publish a monetary amount (see the ticket's verification step).
UPDATE visa_sources
SET active = FALSE
WHERE issuing_body IN (
    'Czech Embassy Cairo',
    'Campus France Egypt',
    'German Embassy Cairo',
    'Spanish Consulate Cairo'
);

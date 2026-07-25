-- GOA-109 (re-scoped): add Sweden — the highest-value uncovered country that passes
-- the "must publish a monetary amount" gate.
--
-- Sweden has 5 programs in the live catalog and the Migration Agency publishes figures
-- directly on its student-permit page. Verified live 2026-07-25 through the ingestion
-- adapter's own fetch path (httpx, no browser needed):
--
--   "The maintenance requirement is at least SEK 10,656 per month, if you applied in 2026"
--   reductions: SEK 2,960/month (free food), SEK 4,736/month (free housing)
--   family:     SEK 4,440/month (spouse/partner), SEK 2,664/month (per child)
--
-- This is also the richest multi-amount source configured so far, so it exercises the
-- funding schema's qualifier field far better than a single flat figure.
--
-- Note the URL structure: migrationsverket.se moved from /English/private-individuals/...
-- to /en/you-want-to-apply/..., which is why the older-style path 404s. Deep government
-- URLs rot; see the ticket's dynamic-discovery recommendation.

INSERT INTO visa_sources (country, visa_type, issuing_body, source_url, fetch_method)
VALUES (
    'Sweden',
    'Residence Permit (Studies)',
    'Swedish Migration Agency',
    'https://www.migrationsverket.se/en/you-want-to-apply/study/higher-education.html',
    'httpx'
)
ON CONFLICT DO NOTHING;

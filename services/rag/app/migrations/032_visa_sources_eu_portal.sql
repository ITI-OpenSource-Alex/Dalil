-- Seed the EU Immigration Portal as the primary source for student funds.
--
-- WHY THIS EXISTS.
--
-- The previous approach gave each country its own national authority and URL.
-- Measured, that reached one usable page in fifteen: six wrong URLs, two sites
-- blocking a plain HTTP client, four JavaScript shells returning under 6 KB of
-- markup, one dead host. Automated discovery did not rescue it -- search finds
-- an official page, rarely the requirements page, and the supervisor correctly
-- rejected most of what it found. Zero rows reached visa_requirements.
--
-- The European Commission publishes a student page per country on one domain,
-- at a URL derived from the country name. All 27 were fetched and returned HTTP
-- 200 with 42-61 KB of content: no blocks, no shells, no dead links. Ten carried
-- an extractable figure on the first pass -- France 615 EUR/month, Finland 560
-- EUR/month and 13,440 EUR for two years, Ireland 7,000 EUR, Poland 30,000 EUR.
--
-- One domain, one template, one page structure. Discovery is not needed for
-- these at all, which removes the component that was failing.
--
-- WHAT THIS DOES NOT REPLACE.
--
-- National sources stay. The portal summarises; an embassy states the operative
-- requirement, and where the two disagree the national authority wins. These
-- rows are the source that reliably yields a number, not the last word on it --
-- so `issuing_body` names the Commission rather than implying a consular
-- authority, and the UI must attribute accordingly.
--
-- The portal is EU-only. The UK is served by its own source, which already
-- returns GBP 1,529 / GBP 1,171 over a plain client.

INSERT INTO visa_sources (country, visa_type, issuing_body, source_url, fetch_method, active)
VALUES
  ('Austria',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-austria_en',     'httpx', true),
  ('Belgium',        'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-belgium_en',     'httpx', true),
  ('Bulgaria',       'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-bulgaria_en',    'httpx', true),
  ('Croatia',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-croatia_en',     'httpx', true),
  ('Cyprus',         'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-cyprus_en',      'httpx', true),
  ('Czech Republic', 'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-czechia_en',     'httpx', true),
  ('Denmark',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-denmark_en',     'httpx', true),
  ('Estonia',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-estonia_en',     'httpx', true),
  ('Finland',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-finland_en',     'httpx', true),
  ('France',         'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-france_en',      'httpx', true),
  ('Germany',        'national student visa',    'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-germany_en',     'httpx', true),
  ('Greece',         'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-greece_en',      'httpx', true),
  ('Hungary',        'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-hungary_en',     'httpx', true),
  ('Ireland',        'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-ireland_en',     'httpx', true),
  ('Italy',          'study visa',               'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-italy_en',       'httpx', true),
  ('Latvia',         'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-latvia_en',      'httpx', true),
  ('Lithuania',      'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-lithuania_en',   'httpx', true),
  ('Luxembourg',     'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-luxembourg_en',  'httpx', true),
  ('Malta',          'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-malta_en',       'httpx', true),
  ('Netherlands',    'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-netherlands_en', 'httpx', true),
  ('Poland',         'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-poland_en',      'httpx', true),
  ('Portugal',       'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-portugal_en',    'httpx', true),
  ('Romania',        'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-romania_en',     'httpx', true),
  ('Slovakia',       'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-slovakia_en',    'httpx', true),
  ('Slovenia',       'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-slovenia_en',    'httpx', true),
  ('Spain',          'student visa',             'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-spain_en',       'httpx', true),
  ('Sweden',         'student residence permit', 'European Commission - EU Immigration Portal', 'https://home-affairs.ec.europa.eu/policies/migration-and-asylum/eu-immigration-portal/student-sweden_en',      'httpx', true)
ON CONFLICT (source_url) DO NOTHING;

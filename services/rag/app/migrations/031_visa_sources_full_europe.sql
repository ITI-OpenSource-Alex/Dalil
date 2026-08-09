-- Extend visa_sources to every country the programme catalogue actually serves.
--
-- The catalogue holds 533 scraped programmes across 30 countries. visa_sources
-- covered 9. A student matching to a programme in one of the other 21 gets a
-- checklist with no visa phase and no financial requirement at all -- the page
-- looks complete while missing the category that decides whether they can go.
--
-- WHAT IS SEEDED HERE, AND WHAT IS NOT.
--
-- Each row names the AUTHORITY that issues the student visa or residence permit
-- for that country. Those are stable public facts: Finland's Migri, Ireland's
-- immigration service, Norway's UDI. They change rarely and are safe to record.
--
-- The URL is NOT asserted. `source_url` is seeded as a discovery placeholder
-- (goa.internal/discover/...) and app/adapters/visa_discovery.py resolves the
-- current official page at ingestion time, filtered to that country's own
-- official domains. Writing URLs by hand is what produced the two NXDOMAIN rows
-- this replaces -- consular links move, and a hardcoded one is a liability with
-- a timer on it.
--
-- The placeholder is deliberately not a real URL: a fetch against it fails
-- loudly and triggers discovery, rather than silently returning something.
--
-- NATIONALITY. Every row is the route for EGYPTIAN applicants. Requirements --
-- and especially the financial figure -- differ by applicant nationality, so a
-- row without that scoping describes a different applicant's journey.

INSERT INTO visa_sources (country, visa_type, issuing_body, source_url, fetch_method, active)
VALUES
  -- Nordics
  ('Denmark',        'student residence permit', 'Danish Agency for International Recruitment and Integration (SIRI)', 'goa.internal/discover/denmark-siri',            'httpx', true),
  ('Finland',        'student residence permit', 'Finnish Immigration Service (Migri)',                                'goa.internal/discover/finland-migri',           'httpx', true),
  ('Norway',         'student residence permit', 'Norwegian Directorate of Immigration (UDI)',                         'goa.internal/discover/norway-udi',              'httpx', true),
  ('Iceland',        'student residence permit', 'Directorate of Immigration Iceland',                                 'goa.internal/discover/iceland-utl',             'httpx', true),

  -- Western Europe
  ('Ireland',        'student visa',             'Irish Immigration Service Delivery',                                 'goa.internal/discover/ireland-immigration',     'httpx', true),
  ('Belgium',        'student visa',             'Belgian Immigration Office',                                         'goa.internal/discover/belgium-dofi',            'httpx', true),
  ('Austria',        'student residence permit', 'Austrian Ministry for European and International Affairs',           'goa.internal/discover/austria-bmeia',           'httpx', true),
  ('Switzerland',    'student residence permit', 'Swiss State Secretariat for Migration (SEM)',                        'goa.internal/discover/switzerland-sem',         'httpx', true),
  ('Portugal',       'student visa',             'Agency for Integration, Migration and Asylum (AIMA)',                'goa.internal/discover/portugal-aima',           'httpx', true),
  ('Greece',         'student visa',             'Hellenic Ministry of Foreign Affairs',                               'goa.internal/discover/greece-mfa',              'httpx', true),
  ('Malta',          'student visa',             'Identita Malta',                                                     'goa.internal/discover/malta-identita',          'httpx', true),
  ('Cyprus',         'student visa',             'Cyprus Civil Registry and Migration Department',                     'goa.internal/discover/cyprus-crmd',             'httpx', true),

  -- Central and Eastern Europe
  ('Poland',         'student visa',             'Polish Office for Foreigners',                                       'goa.internal/discover/poland-udsc',             'httpx', true),
  ('Hungary',        'student residence permit', 'Hungarian National Directorate-General for Aliens Policing',         'goa.internal/discover/hungary-oif',             'httpx', true),
  ('Slovakia',       'student residence permit', 'Slovak Bureau of Border and Foreign Police',                         'goa.internal/discover/slovakia-minv',           'httpx', true),
  ('Romania',        'student visa',             'Romanian General Inspectorate for Immigration',                      'goa.internal/discover/romania-igi',             'httpx', true),
  ('Bulgaria',       'student visa',             'Bulgarian Ministry of Foreign Affairs',                              'goa.internal/discover/bulgaria-mfa',            'httpx', true),
  ('Croatia',        'student residence permit', 'Croatian Ministry of the Interior',                                  'goa.internal/discover/croatia-mup',             'httpx', true),
  ('Estonia',        'student residence permit', 'Estonian Police and Border Guard Board',                             'goa.internal/discover/estonia-politsei',        'httpx', true),
  ('Latvia',         'student residence permit', 'Latvian Office of Citizenship and Migration Affairs',                'goa.internal/discover/latvia-pmlp',             'httpx', true),
  ('Lithuania',      'student residence permit', 'Lithuanian Migration Department',                                    'goa.internal/discover/lithuania-migracija',     'httpx', true)
ON CONFLICT (source_url) DO NOTHING;

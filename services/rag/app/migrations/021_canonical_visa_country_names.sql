-- GOA-111: canonicalize country names across visa_sources / visa_requirements.
--
-- The Profile Matcher's financial gap items (GOA-108) join visa data to programs by
-- country NAME equality. The MastersPortal crawl stores ISO-mapped canonical names
-- ('United Kingdom'), while migration 016 seeded the visa source as 'UK' — so every
-- UK program silently received zero financial items even though the visa row existed
-- with valid pathways and evidence.
--
-- Canonical form is the ISO 3166 short name used by the ingestion adapter's EUROPE_ISO
-- map. Add future visa sources using that spelling.

UPDATE visa_sources SET country = 'United Kingdom' WHERE country IN ('UK', 'U.K.', 'Great Britain');
UPDATE visa_requirements SET country = 'United Kingdom' WHERE country IN ('UK', 'U.K.', 'Great Britain');

UPDATE visa_sources SET country = 'Czech Republic' WHERE country = 'Czechia';
UPDATE visa_requirements SET country = 'Czech Republic' WHERE country = 'Czechia';

UPDATE visa_sources SET country = 'Netherlands' WHERE country IN ('Holland', 'The Netherlands');
UPDATE visa_requirements SET country = 'Netherlands' WHERE country IN ('Holland', 'The Netherlands');

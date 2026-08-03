-- GOA-111 / Option B prerequisite: give program_requirements a filterable discipline.
--
-- /match currently scores EVERY program in the table, two queries per program. That is
-- fine at ~80 programs and fatal at the ~20,000 in-scope European Engineering/CS
-- catalog. Pre-filtering needs two axes: country (already present, matched against the
-- profile's target_countries) and discipline — which did not exist anywhere.
--
-- Values are the canonical slugs from the ingestion adapter's DISCIPLINE_IDS map
-- ('engineering' = MastersPortal discipline 7, 'computer_science' = 24). NULL means
-- "unknown discipline"; such rows must stay eligible so a filtered /match never hides
-- a program merely because its discipline was never recorded.

ALTER TABLE program_requirements
ADD COLUMN IF NOT EXISTS discipline VARCHAR(64) NULL;

-- Partial-friendly composite index for the /match candidate query
-- (WHERE country = ANY(...) AND (discipline = $x OR discipline IS NULL)).
CREATE INDEX IF NOT EXISTS idx_program_requirements_country_discipline
ON program_requirements (country, discipline);

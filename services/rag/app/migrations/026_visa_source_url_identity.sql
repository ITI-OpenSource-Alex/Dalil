-- GOA-041: each configured visa source owns its own content hash.
ALTER TABLE visa_sources
DROP CONSTRAINT IF EXISTS visa_sources_country_visa_type_issuing_body_key;

ALTER TABLE visa_sources
DROP CONSTRAINT IF EXISTS uq_visa_sources_source_url;

ALTER TABLE visa_sources
ADD CONSTRAINT uq_visa_sources_source_url UNIQUE (source_url);

UPDATE visa_requirements
SET source_url = 'https://goa.internal/seed/visa/' || id::text
WHERE source_url IS NULL OR btrim(source_url) = '';

ALTER TABLE visa_requirements
DROP CONSTRAINT IF EXISTS uq_visa_requirements;

ALTER TABLE visa_requirements
ALTER COLUMN source_url SET NOT NULL;

ALTER TABLE visa_requirements
ADD CONSTRAINT uq_visa_requirements_source_url UNIQUE (source_url);

-- GOA-111: Re-key program_requirements unique identity to canonical source_url
-- Seed backfill uses internal namespace https://goa.internal/seed/program/N

UPDATE program_requirements
SET source_url = 'https://goa.internal/seed/program/1'
WHERE id = '11111111-1111-1111-1111-111111111111' AND source_url IS NULL;

UPDATE program_requirements
SET source_url = 'https://goa.internal/seed/program/2'
WHERE id = '22222222-2222-2222-2222-222222222222' AND source_url IS NULL;

UPDATE program_requirements
SET source_url = 'https://goa.internal/seed/program/3'
WHERE id = '33333333-3333-3333-3333-333333333333' AND source_url IS NULL;

-- Backfill any remaining null source_url rows with distinct internal namespace URLs
UPDATE program_requirements
SET source_url = 'https://goa.internal/seed/program/' || id::text
WHERE source_url IS NULL;

ALTER TABLE program_requirements
DROP CONSTRAINT IF EXISTS uq_program_requirements;

ALTER TABLE program_requirements
ADD CONSTRAINT uq_program_requirements_source_url UNIQUE (source_url);

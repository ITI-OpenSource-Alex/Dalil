-- GOA-111 Rollback: Re-instate (university, degree_level, country) constraint.
-- NOTE: This rollback is LOSSY if multiple programs at the same university/degree_level/country
-- were ingested under distinct source_url values.

-- ALTER TABLE program_requirements
-- DROP CONSTRAINT IF EXISTS uq_program_requirements_source_url;

-- ALTER TABLE program_requirements
-- ADD CONSTRAINT uq_program_requirements UNIQUE (university, degree_level, country);

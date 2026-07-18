-- Rollback for 016_add_visa_sources

ALTER TABLE visa_requirements DROP COLUMN IF EXISTS extraction_evidence;
DROP TABLE IF EXISTS visa_sources;

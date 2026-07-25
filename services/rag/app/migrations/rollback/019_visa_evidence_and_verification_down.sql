ALTER TABLE visa_requirements
DROP COLUMN IF EXISTS extraction_evidence,
DROP COLUMN IF EXISTS last_verified_at;

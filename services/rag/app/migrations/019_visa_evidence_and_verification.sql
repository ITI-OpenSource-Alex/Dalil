ALTER TABLE visa_requirements
ADD COLUMN IF NOT EXISTS extraction_evidence JSONB NULL,
ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ NULL;


UPDATE visa_requirements SET proof_of_funds = NULL
WHERE proof_of_funds IS NOT NULL AND NOT (proof_of_funds ? 'pathways');
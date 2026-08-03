-- GOA-111 rollback for 022.
--
-- LOSSY: dropping the column discards every ingested discipline value. They are
-- recoverable only by re-crawling (the MastersPortal API card carries the discipline),
-- so rolling back also re-breaks /match's discipline pre-filter — which is what makes
-- the full catalog scoreable. Prefer fixing forward.

DROP INDEX IF EXISTS idx_program_requirements_country_discipline;

ALTER TABLE program_requirements
DROP COLUMN IF EXISTS discipline;

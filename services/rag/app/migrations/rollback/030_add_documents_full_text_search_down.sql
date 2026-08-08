-- Rollback GOA-137 full-text retrieval support.
DROP INDEX IF EXISTS documents_content_tsv_idx;
ALTER TABLE documents DROP COLUMN IF EXISTS content_tsv;

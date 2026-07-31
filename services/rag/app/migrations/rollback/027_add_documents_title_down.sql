-- Rollback Migration 027: Drop title column
ALTER TABLE documents DROP COLUMN IF EXISTS title;
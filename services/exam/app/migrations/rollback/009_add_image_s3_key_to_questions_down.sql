-- Rollback for migration 009: drop the image_s3_key column.
--
-- run_down_migrations (app/core/database.py) looks for this file under
-- migrations/rollback/<stem>_down.sql when unwinding a batch by
-- MIGRATION_BATCH_ID. Dropping the column is safe: nothing else references it,
-- and NULLs (every non-Academic-Writing row) carry no data to lose.

ALTER TABLE questions
    DROP COLUMN IF EXISTS image_s3_key;

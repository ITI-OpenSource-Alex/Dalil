DROP INDEX IF EXISTS ix_essays_evaluation_cache_key;
ALTER TABLE essays
    DROP COLUMN IF EXISTS evaluation_result,
    DROP COLUMN IF EXISTS evaluation_cache_key,
    DROP COLUMN IF EXISTS exam_type;

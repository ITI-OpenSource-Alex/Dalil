ALTER TABLE essays
    ADD COLUMN IF NOT EXISTS exam_type VARCHAR,
    ADD COLUMN IF NOT EXISTS evaluation_cache_key VARCHAR(64),
    ADD COLUMN IF NOT EXISTS evaluation_result JSONB;

CREATE INDEX IF NOT EXISTS ix_essays_evaluation_cache_key
    ON essays (evaluation_cache_key)
    WHERE evaluation_result IS NOT NULL;

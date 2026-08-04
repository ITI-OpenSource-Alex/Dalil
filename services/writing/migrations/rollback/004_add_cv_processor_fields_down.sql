DROP INDEX IF EXISTS ix_cv_reviews_s3_key_content_hash;
ALTER TABLE cv_reviews
    DROP COLUMN IF EXISTS processed_at,
    DROP COLUMN IF EXISTS error_message,
    DROP COLUMN IF EXISTS structured_data,
    DROP COLUMN IF EXISTS extracted_text,
    DROP COLUMN IF EXISTS content_hash;

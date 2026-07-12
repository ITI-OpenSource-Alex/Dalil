CREATE TABLE IF NOT EXISTS cv_reviews (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    s3_key VARCHAR(512) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'processing',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cv_reviews_user_id ON cv_reviews (user_id);

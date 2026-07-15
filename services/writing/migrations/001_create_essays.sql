CREATE TABLE IF NOT EXISTS essays (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    s3_key VARCHAR,
    extracted_text TEXT NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR NOT NULL DEFAULT 'pending',
    submission_type VARCHAR,
    exam_session_id VARCHAR
);

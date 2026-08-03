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

ALTER TABLE essays ADD COLUMN IF NOT EXISTS task_number INTEGER;
ALTER TABLE essays DROP CONSTRAINT IF EXISTS essays_task_number_check;
ALTER TABLE essays ADD CONSTRAINT essays_task_number_check
    CHECK (task_number IS NULL OR task_number IN (1, 2));
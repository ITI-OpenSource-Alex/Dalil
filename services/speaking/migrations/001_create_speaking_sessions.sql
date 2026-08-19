CREATE TABLE IF NOT EXISTS speaking_sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    question_prompt TEXT NOT NULL,
    question_type VARCHAR(100) NOT NULL,
    transcript TEXT NOT NULL,
    evaluation JSONB NOT NULL, -- Holds detailed per-dimension metrics & examples
    overall_band NUMERIC(2, 1) NOT NULL, -- e.g., 7.5
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);


CREATE INDEX IF NOT EXISTS idx_speaking_sessions_user_id ON speaking_sessions(user_id);
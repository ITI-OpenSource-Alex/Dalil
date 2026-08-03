CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS faq_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_pattern TEXT NOT NULL,
    answer_markdown TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]',
    hit_count INTEGER DEFAULT 0,
    category VARCHAR(100) NULL,
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_faq_question_trgm ON faq_entries USING gin (question_pattern gin_trgm_ops);
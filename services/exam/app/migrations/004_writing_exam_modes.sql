CREATE TABLE IF NOT EXISTS exam_writing_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    task_number INTEGER NOT NULL,
    response_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    evaluation_result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_session_writing_task UNIQUE (session_id, task_number)
);

ALTER TABLE exam_writing_responses ADD CONSTRAINT check_writing_task 
    CHECK (task_number IN (1, 2));

ALTER TABLE exam_writing_responses ADD CONSTRAINT check_word_count_positive 
    CHECK (word_count > 0);

-- NOTE: a Supabase-style RLS policy using auth.uid() was removed here. This project runs
-- plain Postgres (pgvector image) with no `auth` schema, so `auth.uid()` does not exist and
-- the statement aborted the entire migration — leaving BOTH 004 and 005 unapplied, so
-- exam_writing_responses never existed in any environment and the writing questions were
-- never seeded. Ownership is enforced in application code instead (session-ownership checks
-- in the API layer + INTERNAL_API_KEY, plus the Gateway ownership middleware from GOA-059),
-- and the service connects as a single `goa` role, so per-user RLS keyed to an external auth
-- provider would not apply here regardless. No other exam table (exam_sessions, exam_results,
-- exam_speaking_transcripts) uses RLS either.
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

ALTER TABLE exam_writing_responses ENABLE ROW LEVEL SECURITY;

CREATE POLICY writing_owner_only ON exam_writing_responses
    USING (session_id IN (SELECT id FROM exam_sessions WHERE user_id = auth.uid()));
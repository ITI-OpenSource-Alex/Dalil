ALTER TABLE exam_sessions
ADD COLUMN IF NOT EXISTS question_id UUID
    REFERENCES questions(id)
    ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_exam_sessions_question
ON exam_sessions(question_id);

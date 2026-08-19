CREATE TABLE IF NOT EXISTS exam_speaking_transcripts (

    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    part  INTEGER NOT NULL,
    transcript_text TEXT NOT NULL,
    duration_s INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_session_part UNIQUE (session_id, part)
);

    


ALTER TABLE exam_results ADD COLUMN IF NOT EXISTS agent_responses JSONB;



ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_skill_area_check;
ALTER TABLE questions ADD CONSTRAINT questions_skill_area_check 
    CHECK (skill_area IN ('reading', 'listening', 'speaking', 'writing'));

ALTER TABLE exam_results DROP CONSTRAINT IF EXISTS exam_results_skill_area_check;
ALTER TABLE exam_results ADD CONSTRAINT exam_results_skill_area_check
    CHECK (skill_area IN ('reading', 'listening', 'speaking', 'writing'));
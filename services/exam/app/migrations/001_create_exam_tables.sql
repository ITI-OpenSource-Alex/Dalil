CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE TABLE IF NOT EXISTS exam_sessions (

   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    exam_type VARCHAR(20) NOT NULL
        CHECK (exam_type IN ('academic', 'general')),

    skill_area VARCHAR(20) NOT NULL
        CHECK (skill_area IN ('reading', 'listening', 'writing', 'speaking')),

    status VARCHAR(20) NOT NULL
        CHECK (status IN ('pending', 'in_progress', 'submitted', 'scored')),

    started_at TIMESTAMPTZ,

    submitted_at TIMESTAMPTZ,

    time_limit_seconds INTEGER NOT NULL

);
CREATE TABLE IF NOT EXISTS questions (

   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    book_ref TEXT NOT NULL,

    test_number INTEGER NOT NULL,

    exam_type VARCHAR(20) NOT NULL
        CHECK (exam_type IN ('academic', 'general')),

    skill_area VARCHAR(20) NOT NULL
        CHECK (skill_area IN ('reading', 'listening')),

    passage_text TEXT,

    audio_s3_key TEXT,

    questions JSONB NOT NULL,

    answer_key JSONB NOT NULL

);

CREATE TABLE IF NOT EXISTS exam_results (

   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL
        REFERENCES exam_sessions(id)
        ON DELETE CASCADE,

    user_id UUID NOT NULL,

    skill_area VARCHAR(20) NOT NULL
        CHECK (skill_area IN ('reading', 'listening', 'writing', 'speaking')),

    raw_score INTEGER NOT NULL,

    band_score DECIMAL(3,1) NOT NULL,

    section_scores JSONB,

    graded_at TIMESTAMPTZ NOT NULL

);
CREATE INDEX idx_exam_sessions_user
ON exam_sessions(user_id);
CREATE INDEX idx_questions_type_skill
ON questions(exam_type, skill_area);
CREATE INDEX idx_exam_results_session
ON exam_results(session_id);
CREATE INDEX idx_exam_results_user
ON exam_results(user_id);
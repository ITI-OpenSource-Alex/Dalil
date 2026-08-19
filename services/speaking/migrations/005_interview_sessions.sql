CREATE TABLE IF NOT EXISTS speaking_interview_sessions (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    bank_version VARCHAR(128) NOT NULL,
    bank_sha256 CHAR(64) NOT NULL,
    cue_id VARCHAR(128) NOT NULL,
    voice_id VARCHAR(128) NOT NULL,
    audio_format VARCHAR(128) NOT NULL,
    selection JSONB NOT NULL,
    snapshot JSONB NOT NULL,
    partial BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_speaking_interviews_user_updated
    ON speaking_interview_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS speaking_interview_turns (
    session_id UUID NOT NULL REFERENCES speaking_interview_sessions(id) ON DELETE CASCADE,
    turn_id VARCHAR(32) NOT NULL,
    part SMALLINT NOT NULL CHECK (part BETWEEN 1 AND 3),
    question_id VARCHAR(160) NOT NULL,
    speaker VARCHAR(16) NOT NULL CHECK (speaker IN ('examiner', 'candidate')),
    text TEXT NOT NULL,
    audio_ref TEXT,
    words JSONB NOT NULL DEFAULT '[]'::jsonb,
    start_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    end_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, turn_id)
);

CREATE INDEX IF NOT EXISTS idx_speaking_interview_turns_order
    ON speaking_interview_turns(session_id, turn_id);

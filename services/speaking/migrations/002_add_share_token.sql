ALTER TABLE speaking_sessions
    ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) UNIQUE;

CREATE INDEX IF NOT EXISTS idx_speaking_sessions_share_token ON speaking_sessions(share_token);

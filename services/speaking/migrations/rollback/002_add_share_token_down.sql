DROP INDEX IF EXISTS idx_speaking_sessions_share_token;
ALTER TABLE speaking_sessions DROP COLUMN IF EXISTS share_token;

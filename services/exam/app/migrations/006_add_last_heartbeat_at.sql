ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ;

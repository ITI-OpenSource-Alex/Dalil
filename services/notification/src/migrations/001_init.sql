CREATE TABLE IF NOT EXISTS notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id VARCHAR(64)  NOT NULL UNIQUE,
    user_id         VARCHAR(128) NOT NULL,
    type            VARCHAR(40)  NOT NULL,
    title           TEXT         NOT NULL,
    body            TEXT         NOT NULL,
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;

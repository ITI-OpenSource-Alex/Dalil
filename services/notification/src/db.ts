import pg from 'pg';

const { Pool } = pg;

const connectionString = process.env.DATABASE_URL || 'postgres://postgres:postgres@localhost:5432/notification_db';

export const pool = new Pool({
    connectionString,
    max: 5,
    idleTimeoutMillis: 30000,
});

const INIT_SQL = `
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
`;

let migrationRan = false;

export async function runMigrations(): Promise<void> {
    if (migrationRan) return;
    const client = await pool.connect();
    try {
        await client.query(INIT_SQL);
        migrationRan = true;
    } finally {
        client.release();
    }
}

export interface InsertNotificationParams {
    notificationId: string;
    userId: string;
    type: string;
    title: string;
    body: string;
}

export async function insertNotification(params: InsertNotificationParams): Promise<boolean> {
    await runMigrations();
    const query = `
        INSERT INTO notifications (notification_id, user_id, type, title, body)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (notification_id) DO NOTHING;
    `;
    const values = [params.notificationId, params.userId, params.type, params.title, params.body];
    const result = await pool.query(query, values);
    return (result.rowCount ?? 0) > 0;
}

export interface NotificationRecord {
    id: string;
    notificationId: string;
    userId: string;
    type: string;
    title: string;
    body: string;
    readAt: string | null;
    createdAt: string;
}

export async function getUnreadNotifications(userId: string): Promise<NotificationRecord[]> {
    await runMigrations();
    const query = `
        SELECT id, notification_id, user_id, type, title, body, read_at, created_at
        FROM notifications
        WHERE user_id = $1 AND read_at IS NULL
        ORDER BY created_at DESC;
    `;
    const result = await pool.query(query, [userId]);
    return result.rows.map(row => ({
        id: row.id,
        notificationId: row.notification_id,
        userId: row.user_id,
        type: row.type,
        title: row.title,
        body: row.body,
        readAt: row.read_at ? row.read_at.toISOString() : null,
        createdAt: row.created_at.toISOString(),
    }));
}

export async function deleteNotificationsForUser(userId: string): Promise<number> {
    await runMigrations();
    const result = await pool.query('DELETE FROM notifications WHERE user_id = $1', [userId]);
    return result.rowCount ?? 0;
}

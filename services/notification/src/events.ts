import crypto from 'crypto';
import type { NotificationEvent } from '../../../packages/contracts/ts/index.js';

export function deriveNotificationId(event: NotificationEvent): string {
    let rawKey = '';
    switch (event.eventType) {
        case 'ScholarshipMatched':
        case 'DEADLINE_REMINDER':
            rawKey = `${event.eventType}:${event.userId}:${event.programId}:${event.cycleDate}`;
            break;
        case 'CVProcessed':
            rawKey = `${event.eventType}:${event.userId}:${event.cvId}:${event.status}:${event.timestamp || ''}`;
            break;
    }
    return crypto.createHash('sha256').update(rawKey).digest('hex');
}

export function parseNotificationEvent(body: string): NotificationEvent {
    const data = JSON.parse(body);
    const eventType = data.eventType;
    if (eventType === 'ScholarshipMatched' || eventType === 'DEADLINE_REMINDER' || eventType === 'CVProcessed') {
        return data as NotificationEvent;
    }
    throw new Error(`Unrecognised notification eventType: ${eventType}`);
}

export interface AccountDeletedEvent {
    type: 'account.deleted';
    payload: {
        userId: string;
        deletedAt: string;
    };
}

export function parseAccountDeletedEvent(body: string): AccountDeletedEvent | null {
    const data = JSON.parse(body);
    const event = data.Type === 'Notification' && data.Message ? JSON.parse(data.Message) : data;
    if (event.type !== 'account.deleted') return null;
    if (!event.payload?.userId) throw new Error('AccountDeleted event missing payload.userId');
    return event as AccountDeletedEvent;
}

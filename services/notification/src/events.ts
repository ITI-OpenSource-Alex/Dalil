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

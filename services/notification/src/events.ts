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

// --- GOA-083: transactional auth emails ------------------------------------
//
// These two events are published by the User service on the SES → SQS refactor.
// Unlike the ScholarshipMatched / CVProcessed events above, they are a flat
// shape keyed on `type` (not `eventType`) and they carry the recipient `email`
// inline — so the handler sends directly and never calls lookupUserEmail().
// The payloads are the exact contract agreed with the User service:
//   { type: 'PasswordResetRequested',    userId, resetToken, email, expiresAt }
//   { type: 'EmailVerificationRequired', userId, verificationToken, email }

export interface PasswordResetRequestedEvent {
    type: 'PasswordResetRequested';
    userId: string;
    resetToken: string;
    email: string;
    expiresAt: string;
}

export interface EmailVerificationRequiredEvent {
    type: 'EmailVerificationRequired';
    userId: string;
    verificationToken: string;
    email: string;
}

export type AuthEmailEvent =
    | PasswordResetRequestedEvent
    | EmailVerificationRequiredEvent;

/**
 * Returns the parsed auth-email event, or null when the body is some other
 * event type (so the caller can fall through to parseNotificationEvent).
 * Throws only when the body IS an auth event but is missing required fields —
 * that lands the record in batchItemFailures for redelivery rather than
 * sending mail with a broken link.
 */
export function parseAuthEmailEvent(body: string): AuthEmailEvent | null {
    const data = JSON.parse(body);
    // Support both raw SQS delivery and SNS-wrapped, matching parseAccountDeletedEvent.
    const event = data.Type === 'Notification' && data.Message ? JSON.parse(data.Message) : data;

    if (event.type === 'PasswordResetRequested') {
        if (!event.userId || !event.resetToken || !event.email) {
            throw new Error('PasswordResetRequested event missing userId, resetToken or email');
        }
        return event as PasswordResetRequestedEvent;
    }

    if (event.type === 'EmailVerificationRequired') {
        if (!event.userId || !event.verificationToken || !event.email) {
            throw new Error('EmailVerificationRequired event missing userId, verificationToken or email');
        }
        return event as EmailVerificationRequiredEvent;
    }

    return null;
}

/**
 * Deterministic idempotency key for an auth email. Keyed on the token so a
 * redelivered SQS message renders the same key and is deduped, but a genuinely
 * new reset/verification request (new token) is allowed through.
 */
export function deriveAuthEmailId(event: AuthEmailEvent): string {
    const token =
        event.type === 'PasswordResetRequested' ? event.resetToken : event.verificationToken;
    const rawKey = `${event.type}:${event.userId}:${token}`;
    return crypto.createHash('sha256').update(rawKey).digest('hex');
}

import { deriveNotificationId, parseAccountDeletedEvent, parseNotificationEvent, parseAuthEmailEvent, deriveAuthEmailId } from '../../src/events';
import { ScholarshipMatchedNotification, DeadlineReminderNotification, CVProcessedNotification } from '../../../../packages/contracts/ts/index';

describe('Event Parsing & Idempotency Key Derivation', () => {
    it('should parse real producer ScholarshipMatched payload', () => {
        const rawJson = JSON.stringify({
            eventType: 'ScholarshipMatched',
            userId: 'user_123',
            programId: 'prog_daad',
            programName: 'DAAD EPOS',
            provider: 'DAAD',
            country: 'Germany',
            deadline: '2026-10-15',
            score: 87.5,
            cycleDate: '2026-07-29',
        });

        const event = parseNotificationEvent(rawJson) as ScholarshipMatchedNotification;
        expect(event.eventType).toBe('ScholarshipMatched');
        expect(event.userId).toBe('user_123');
        expect(event.score).toBe(87.5);
    });

    it('should parse DEADLINE_REMINDER payload', () => {
        const rawJson = JSON.stringify({
            eventType: 'DEADLINE_REMINDER',
            userId: 'user_123',
            programId: 'prog_daad',
            programName: 'DAAD EPOS',
            provider: 'DAAD',
            country: 'Germany',
            deadline: '2026-10-15',
            score: 90.0,
            cycleDate: '2026-07-29',
        });

        const event = parseNotificationEvent(rawJson) as DeadlineReminderNotification;
        expect(event.eventType).toBe('DEADLINE_REMINDER');
    });

    it('should parse CVProcessed payload', () => {
        const rawJson = JSON.stringify({
            eventType: 'CVProcessed',
            userId: 'user_456',
            cvId: 42,
            s3Key: 'cvs/user_456/cv_42.pdf',
            status: 'ready',
        });

        const event = parseNotificationEvent(rawJson) as CVProcessedNotification;
        expect(event.eventType).toBe('CVProcessed');
        expect(event.cvId).toBe(42);
    });

    it('should throw on unsupported eventType', () => {
        const rawJson = JSON.stringify({ eventType: 'UNKNOWN_EVENT' });
        expect(() => parseNotificationEvent(rawJson)).toThrow('Unrecognised notification eventType');
    });

    it('should parse AccountDeleted from an SNS envelope', () => {
        const message = {
            type: 'account.deleted',
            payload: {
                userId: 'user_123',
                deletedAt: '2026-08-02T10:00:00.000Z',
            },
        };
        const rawJson = JSON.stringify({
            Type: 'Notification',
            Message: JSON.stringify(message),
        });

        const event = parseAccountDeletedEvent(rawJson);

        expect(event?.type).toBe('account.deleted');
        expect(event?.payload.userId).toBe('user_123');
    });

    it('should produce deterministic sha256 notificationId', () => {
        const event: ScholarshipMatchedNotification = {
            eventType: 'ScholarshipMatched',
            userId: 'u1',
            programId: 'p1',
            programName: 'DAAD',
            provider: 'DAAD',
            country: 'Germany',
            deadline: '2026-10-15',
            score: 85,
            cycleDate: '2026-07-29',
        };

        const id1 = deriveNotificationId(event);
        const id2 = deriveNotificationId(event);

        expect(id1).toBe(id2);
        expect(id1).toHaveLength(64);
    });
});

describe('GOA-083 Auth Email Event Parsing', () => {
    it('should parse a PasswordResetRequested event with the exact User-service payload', () => {
        const rawJson = JSON.stringify({
            type: 'PasswordResetRequested',
            userId: 'user_123',
            resetToken: 'raw-reset-token-abc',
            email: 'lina@example.com',
            expiresAt: '2026-07-29T12:00:00.000Z',
        });

        const event = parseAuthEmailEvent(rawJson);
        expect(event).not.toBeNull();
        expect(event!.type).toBe('PasswordResetRequested');
        expect(event!.email).toBe('lina@example.com');
    });

    it('should parse an EmailVerificationRequired event with the exact User-service payload', () => {
        const rawJson = JSON.stringify({
            type: 'EmailVerificationRequired',
            userId: 'user_456',
            verificationToken: 'raw-verify-token-xyz',
            email: 'omar@example.com',
        });

        const event = parseAuthEmailEvent(rawJson);
        expect(event).not.toBeNull();
        expect(event!.type).toBe('EmailVerificationRequired');
        expect(event!.email).toBe('omar@example.com');
    });

    it('should return null for a non-auth event so the caller falls through', () => {
        const rawJson = JSON.stringify({
            eventType: 'ScholarshipMatched',
            userId: 'user_1',
        });
        expect(parseAuthEmailEvent(rawJson)).toBeNull();
    });

    it('should throw when a PasswordResetRequested event is missing its token', () => {
        const rawJson = JSON.stringify({
            type: 'PasswordResetRequested',
            userId: 'user_123',
            email: 'lina@example.com',
        });
        expect(() => parseAuthEmailEvent(rawJson)).toThrow(
            'PasswordResetRequested event missing userId, resetToken or email',
        );
    });

    it('should throw when an EmailVerificationRequired event is missing its email', () => {
        const rawJson = JSON.stringify({
            type: 'EmailVerificationRequired',
            userId: 'user_456',
            verificationToken: 'raw-verify-token-xyz',
        });
        expect(() => parseAuthEmailEvent(rawJson)).toThrow(
            'EmailVerificationRequired event missing userId, verificationToken or email',
        );
    });

    it('should derive a deterministic, token-scoped idempotency id', () => {
        const first = deriveAuthEmailId({
            type: 'PasswordResetRequested',
            userId: 'u1',
            resetToken: 'token-A',
            email: 'a@example.com',
            expiresAt: '2026-07-29T12:00:00.000Z',
        });
        const same = deriveAuthEmailId({
            type: 'PasswordResetRequested',
            userId: 'u1',
            resetToken: 'token-A',
            email: 'a@example.com',
            expiresAt: '2026-07-29T13:00:00.000Z',
        });
        const differentToken = deriveAuthEmailId({
            type: 'PasswordResetRequested',
            userId: 'u1',
            resetToken: 'token-B',
            email: 'a@example.com',
            expiresAt: '2026-07-29T12:00:00.000Z',
        });

        // Same token → same id (redelivery is deduped); different token → different id.
        expect(first).toBe(same);
        expect(first).not.toBe(differentToken);
        expect(first).toHaveLength(64);
    });
});

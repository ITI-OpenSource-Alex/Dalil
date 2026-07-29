import { deriveNotificationId, parseNotificationEvent } from '../../src/events';
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

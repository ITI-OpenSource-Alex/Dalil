import { renderNotificationTemplate } from '../../src/templates';
import { ScholarshipMatchedNotification, DeadlineReminderNotification, CVProcessedNotification } from '../../../../packages/contracts/ts/index';

describe('Handlebars Templates Rendering', () => {
    it('should render scholarship match template with data and HTML escaping', () => {
        const event: ScholarshipMatchedNotification = {
            eventType: 'ScholarshipMatched',
            userId: 'user_1',
            programId: 'p1',
            programName: '<script>alert("xss")</script> DAAD',
            provider: 'DAAD',
            country: 'Germany',
            deadline: '2026-10-15',
            score: 95.5,
            cycleDate: '2026-07-29',
        };

        const rendered = renderNotificationTemplate(event);
        expect(rendered.title).toContain('DAAD');
        expect(rendered.body).toContain('&lt;script&gt;');
        expect(rendered.body).not.toContain('<script>');
        expect(rendered.body).toContain('95.5%');
    });

    it('should render template safely when nullable fields are null', () => {
        const event: ScholarshipMatchedNotification = {
            eventType: 'ScholarshipMatched',
            userId: 'user_1',
            programId: 'p1',
            programName: null,
            provider: null,
            country: null,
            deadline: null,
            score: 80,
            cycleDate: '2026-07-29',
        };

        const rendered = renderNotificationTemplate(event);
        expect(rendered.body).not.toContain('null');
        expect(rendered.body).not.toContain('undefined');
    });

    it('should render deadline reminder template', () => {
        const event: DeadlineReminderNotification = {
            eventType: 'DEADLINE_REMINDER',
            userId: 'user_1',
            programId: 'p1',
            programName: 'DAAD EPOS',
            provider: 'DAAD',
            country: 'Germany',
            deadline: '2026-10-15',
            score: 88,
            cycleDate: '2026-07-29',
        };

        const rendered = renderNotificationTemplate(event);
        expect(rendered.title).toContain('Deadline Approaching');
        expect(rendered.body).toContain('DAAD EPOS');
    });

    it('should render CV processed template', () => {
        const event: CVProcessedNotification = {
            eventType: 'CVProcessed',
            userId: 'user_1',
            cvId: 101,
            s3Key: 'cvs/u1/101.pdf',
            status: 'ready',
        };

        const rendered = renderNotificationTemplate(event);
        expect(rendered.title).toBe('CV Analysis Complete');
        expect(rendered.body).toContain('101');
    });
});

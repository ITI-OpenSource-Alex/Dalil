import fs from 'fs';
import path from 'path';
import Handlebars from 'handlebars';
import type { NotificationEvent } from '../../../packages/contracts/ts/index.js';

export interface RenderedTemplate {
    title: string;
    body: string;
}

const templatesDir = path.resolve(process.cwd(), 'templates');

function loadTemplate(filename: string): Handlebars.TemplateDelegate {
    const filePath = path.join(templatesDir, filename);
    if (!fs.existsSync(filePath)) {
        // Fallback for dist layout
        const fallbackPath = path.resolve(__dirname, '../templates', filename);
        const content = fs.readFileSync(fallbackPath, 'utf-8');
        return Handlebars.compile(content);
    }
    const content = fs.readFileSync(filePath, 'utf-8');
    return Handlebars.compile(content);
}

export function renderNotificationTemplate(event: NotificationEvent): RenderedTemplate {
    switch (event.eventType) {
        case 'ScholarshipMatched': {
            const template = loadTemplate('scholarship-match.hbs');
            const title = `New Scholarship Match: ${event.programName || 'Scholarship Opportunity'}`;
            const body = template(event);
            return { title, body };
        }
        case 'DEADLINE_REMINDER': {
            const template = loadTemplate('deadline-reminder.hbs');
            const title = `Urgent Reminder: ${event.programName || 'Scholarship'} Deadline Approaching`;
            const body = template(event);
            return { title, body };
        }
        case 'CVProcessed': {
            const template = loadTemplate('cv-processed.hbs');
            const title = `CV Analysis ${event.status === 'ready' ? 'Complete' : 'Failed'}`;
            const body = template(event);
            return { title, body };
        }
        default: {
            const _exhaustive: never = event;
            throw new Error(`Unsupported event type: ${JSON.stringify(_exhaustive)}`);
        }
    }
}

import { SQSEvent, SQSBatchResponse, ALBEvent, ALBResult } from 'aws-lambda';
import { parseNotificationEvent, deriveNotificationId } from './events.js';
import { insertNotification, getUnreadNotifications } from './db.js';
import { renderNotificationTemplate } from './templates.js';
import { sendEmail } from './ses.js';
import { lookupUserEmail } from './users.js';

export const isSqsEvent = (e: any): e is SQSEvent =>
    Array.isArray(e?.Records) && e.Records[0]?.eventSource === 'aws:sqs';

export const isAlbEvent = (e: any): e is ALBEvent =>
    Boolean(e?.requestContext?.elb);

export async function handleSqsBatch(event: SQSEvent): Promise<SQSBatchResponse> {
    const failedIds: string[] = [];

    for (const record of event.Records) {
        try {
            const notifEvent = parseNotificationEvent(record.body);
            const notificationId = deriveNotificationId(notifEvent);
            const rendered = renderNotificationTemplate(notifEvent);

            // Step 1: Insert into DB first (ON CONFLICT DO NOTHING)
            const inserted = await insertNotification({
                notificationId,
                userId: notifEvent.userId,
                type: notifEvent.eventType,
                title: rendered.title,
                body: rendered.body,
            });

            // Step 2: If inserted (not a duplicate), send the email.
            //
            // The recipient is looked up from the User service. No event on
            // these queues carries an email address, so there is nothing to
            // read off the message — see src/users.ts. A failed lookup throws,
            // which lands this record in batchItemFailures for retry rather
            // than sending mail to an address that does not exist.
            if (inserted) {
                const recipientEmail = await lookupUserEmail(notifEvent.userId);
                await sendEmail({
                    recipientEmail,
                    subject: rendered.title,
                    htmlBody: rendered.body,
                });
            }
        } catch (error) {
            console.error(`Error processing SQS record ${record.messageId}:`, error);
            failedIds.push(record.messageId);
        }
    }

    return {
        batchItemFailures: failedIds.map(id => ({ itemIdentifier: id })),
    };
}

export async function handleHttp(event: ALBEvent): Promise<ALBResult> {
    try {
        const userId = event.headers?.['x-user-id'] || event.headers?.['X-User-ID'] || event.queryStringParameters?.['userId'];

        if (!userId) {
            return {
                statusCode: 400,
                statusDescription: '400 Bad Request',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ error: 'Missing userId parameter/header' }),
                isBase64Encoded: false,
            };
        }

        const notifications = await getUnreadNotifications(userId);

        return {
            statusCode: 200,
            statusDescription: '200 OK',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notifications }),
            isBase64Encoded: false,
        };
    } catch (error: any) {
        console.error('Error handling ALB HTTP request:', error);
        return {
            statusCode: 500,
            statusDescription: '500 Internal Server Error',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error: 'Internal server error' }),
            isBase64Encoded: false,
        };
    }
}

export const handler = async (event: unknown) => {
    if (isSqsEvent(event)) {
        return handleSqsBatch(event);
    }
    if (isAlbEvent(event)) {
        return handleHttp(event);
    }
    throw new Error(`Unrecognised event shape: ${JSON.stringify(event).slice(0, 200)}`);
};

import { SQSEvent, SQSBatchResponse, ALBEvent, ALBResult } from 'aws-lambda';
import { parseNotificationEvent, deriveNotificationId, parseAccountDeletedEvent } from './events.js';
import { insertNotification, getUnreadNotifications, deleteNotificationsForUser } from './db.js';
import { renderNotificationTemplate } from './templates.js';
import { sendEmail } from './ses.js';
import { lookupUserEmail } from './users.js';

let coldStart = true;

function memoryUsedMb(): number {
    return Math.round((process.memoryUsage().rss / 1024 / 1024) * 100) / 100;
}

function logInvocation(params: {
    functionName: string;
    requestId: string | undefined;
    durationMs: number;
    recordsProcessed: number;
    outcome: string;
}) {
    console.log(JSON.stringify({
        function_name: params.functionName,
        request_id: params.requestId,
        duration_ms: Math.round(params.durationMs * 100) / 100,
        memory_used_mb: memoryUsedMb(),
        cold_start: coldStart,
        records_processed: params.recordsProcessed,
        outcome: params.outcome,
    }));
    coldStart = false;
}

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

export const handler = async (event: unknown, context?: { awsRequestId?: string; functionName?: string }) => {
    const started = Date.now();
    const functionName = context?.functionName || 'goa-notification-sender';
    const requestId = context?.awsRequestId;
    let recordsProcessed = 0;
    let outcome = 'success';

    try {
        if (isSqsEvent(event)) {
            recordsProcessed = event.Records.length;
            const result = await handleSqsBatch(event);
            if ((result.batchItemFailures || []).length > 0) {
                outcome = 'partial_failure';
            }
            return result;
        }
        if (isAlbEvent(event)) {
            const result = await handleHttp(event);
            return result;
        }
        outcome = 'fail';
        throw new Error(`Unrecognised event shape: ${JSON.stringify(event).slice(0, 200)}`);
    } finally {
        logInvocation({
            functionName,
            requestId,
            durationMs: Date.now() - started,
            recordsProcessed,
            outcome,
        });
    }
};


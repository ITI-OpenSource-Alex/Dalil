/**
 * LOCAL DEVELOPMENT ONLY. Not used in AWS.
 *
 * In AWS this service is a Lambda: an SQS event source mapping delivers batches
 * to `handleSqsBatch`, and an ALB Lambda target group delivers HTTP requests to
 * `handleHttp`. Neither exists locally, so without this file the service cannot
 * run against docker compose at all — and the whole point of the GOA-023 plan's
 * local-first strategy is that the full chain can be proven for free before
 * anything is deployed.
 *
 * This provides the two things AWS provides:
 *
 *   1. An HTTP server on PORT, so the Gateway can reach GET /api/notifications
 *      and receive plain JSON. It unwraps the ALB response envelope that
 *      handleHttp returns, because the Gateway proxies to a normal HTTP service
 *      locally, not to an ALB Lambda target.
 *   2. A poller that reads notification-queue and hands batches to
 *      handleSqsBatch, deleting the messages it processed successfully. This
 *      stands in for the event source mapping.
 *
 * It deliberately reuses handleSqsBatch and handleHttp rather than
 * reimplementing them. A local harness that duplicates the logic would prove the
 * harness works, not the handler — which is the failure mode this whole service
 * is prone to.
 */

import http from 'http';
import {
    SQSClient,
    ReceiveMessageCommand,
    DeleteMessageBatchCommand,
} from '@aws-sdk/client-sqs';
import type { SQSEvent, SQSRecord, ALBEvent } from 'aws-lambda';
import { handleSqsBatch, handleHttp } from './handler.js';

const PORT = Number(process.env.PORT || 8087);
const QUEUE_URLS = (process.env.NOTIFICATION_QUEUE_URLS || '')
    .split(',')
    .map(u => u.trim())
    .filter(Boolean);
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || 5000);

const sqs = new SQSClient({
    region: process.env.AWS_REGION || 'us-east-1',
    ...(process.env.LOCALSTACK_ENDPOINT ? { endpoint: process.env.LOCALSTACK_ENDPOINT } : {}),
});

// --- HTTP -------------------------------------------------------------------

const server = http.createServer(async (req, res) => {
    try {
        if (req.url?.startsWith('/health')) {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'ok', service: 'notification' }));
            return;
        }

        if (req.method === 'GET' && req.url?.startsWith('/api/notifications')) {
            const url = new URL(req.url, `http://localhost:${PORT}`);
            // Shape the request the way an ALB target would deliver it, so
            // handleHttp runs exactly as it will in AWS.
            const albEvent = {
                requestContext: { elb: { targetGroupArn: 'local' } },
                httpMethod: 'GET',
                path: url.pathname,
                queryStringParameters: Object.fromEntries(url.searchParams),
                headers: req.headers as Record<string, string>,
                body: null,
                isBase64Encoded: false,
            } as unknown as ALBEvent;

            const result = await handleHttp(albEvent);
            // Unwrap the envelope: the Gateway talks to this as an ordinary
            // HTTP service locally.
            res.writeHead(result.statusCode ?? 200, {
                'Content-Type': 'application/json',
            });
            res.end(result.body ?? '{}');
            return;
        }

        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'not found' }));
    } catch (error) {
        console.error('local-server error', error);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'internal error' }));
    }
});

// --- SQS poller -------------------------------------------------------------

function toSqsRecord(message: { MessageId?: string; ReceiptHandle?: string; Body?: string }, queueUrl: string): SQSRecord {
    return {
        messageId: message.MessageId ?? '',
        receiptHandle: message.ReceiptHandle ?? '',
        body: message.Body ?? '',
        attributes: {} as SQSRecord['attributes'],
        messageAttributes: {},
        md5OfBody: '',
        eventSource: 'aws:sqs',
        eventSourceARN: queueUrl,
        awsRegion: process.env.AWS_REGION || 'us-east-1',
    };
}

async function pollOnce(queueUrl: string): Promise<void> {
    const received = await sqs.send(
        new ReceiveMessageCommand({
            QueueUrl: queueUrl,
            MaxNumberOfMessages: 10,
            WaitTimeSeconds: 1,
        }),
    );

    const messages = received.Messages ?? [];
    if (messages.length === 0) return;

    const event: SQSEvent = {
        Records: messages.map(m => toSqsRecord(m, queueUrl)),
    };

    const response = await handleSqsBatch(event);
    const failed = new Set(response.batchItemFailures.map(f => f.itemIdentifier));

    // Delete only what succeeded, so failures redeliver and eventually reach the
    // DLQ — matching how SQS behaves with ReportBatchItemFailures in AWS.
    const toDelete = messages
        .filter(m => !failed.has(m.MessageId ?? ''))
        .map(m => ({ Id: m.MessageId!, ReceiptHandle: m.ReceiptHandle! }));

    if (toDelete.length > 0) {
        await sqs.send(new DeleteMessageBatchCommand({ QueueUrl: queueUrl, Entries: toDelete }));
    }

    console.log(
        `[poller] ${queueUrl.split('/').pop()}: processed ${messages.length}, ` +
        `deleted ${toDelete.length}, failed ${failed.size}`,
    );
}

async function pollForever(): Promise<void> {
    if (QUEUE_URLS.length === 0) {
        console.warn('[poller] NOTIFICATION_QUEUE_URLS is empty — not polling any queue');
        return;
    }
    console.log(`[poller] watching: ${QUEUE_URLS.join(', ')}`);
    for (;;) {
        for (const queueUrl of QUEUE_URLS) {
            try {
                await pollOnce(queueUrl);
            } catch (error) {
                console.error(`[poller] error on ${queueUrl}`, error);
            }
        }
        await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS));
    }
}

server.listen(PORT, () => {
    console.log(`notification local server listening on ${PORT}`);
    void pollForever();
});

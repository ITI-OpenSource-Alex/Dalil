import { SESClient, SendEmailCommand } from '@aws-sdk/client-ses';

const region = process.env.AWS_REGION || 'eu-west-1';
const endpoint = process.env.LOCALSTACK_ENDPOINT || process.env.AWS_SES_ENDPOINT;

export const sesClient = new SESClient({
    region,
    ...(endpoint ? { endpoint } : {}),
});

export interface SendEmailParams {
    recipientEmail: string;
    subject: string;
    htmlBody: string;
}

export async function sendEmail(params: SendEmailParams): Promise<string> {
    // No default sender. The previous fallback was notifications@staging.goa.app,
    // on a domain the project does not own — SES can never verify it, so every
    // send would be rejected while the code looked configured. Failing here is
    // louder and cheaper to diagnose than a rejected send.
    //
    // The verified individual address goes in SES_SENDER_ADDRESS; see the
    // GOA-023 plan, decision 3.3.
    const sender = process.env.SES_SENDER_ADDRESS;
    if (!sender) {
        throw new Error(
            'SES_SENDER_ADDRESS is not set. It must be an address verified in SES — ' +
            'the project owns no domain, so this is an individual verified identity.',
        );
    }
    const command = new SendEmailCommand({
        Source: sender,
        Destination: {
            ToAddresses: [params.recipientEmail],
        },
        Message: {
            Subject: { Data: params.subject, Charset: 'UTF-8' },
            Body: {
                Html: { Data: params.htmlBody, Charset: 'UTF-8' },
            },
        },
    });

    const response = await sesClient.send(command);
    return response.MessageId || 'msg-sent';
}

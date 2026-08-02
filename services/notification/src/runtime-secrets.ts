import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';

let loaded = false;

export async function loadNotificationRuntimeSecrets(): Promise<void> {
    if (loaded) return;
    const secretArn = process.env.NOTIFICATION_SECRET_ARN;
    if (!secretArn) {
        loaded = true;
        return;
    }

    const client = new SecretsManagerClient({
        region: process.env.AWS_REGION || 'eu-west-1',
        ...(process.env.LOCALSTACK_ENDPOINT ? { endpoint: process.env.LOCALSTACK_ENDPOINT } : {}),
    });
    const response = await client.send(new GetSecretValueCommand({ SecretId: secretArn }));
    const values = JSON.parse(response.SecretString || '{}') as Record<string, unknown>;
    for (const [key, value] of Object.entries(values)) {
        if (value !== undefined && value !== null && !process.env[key]) {
            process.env[key] = String(value);
        }
    }
    loaded = true;
}

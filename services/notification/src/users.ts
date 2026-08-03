/**
 * Resolve a user's real email address from the User service.
 *
 * None of the events on notification-queue carry an email. The scholarship
 * matcher publishes userId, programId, programName, provider, country,
 * deadline, score and cycleDate — and nothing else. CVProcessed carries userId,
 * cvId, s3Key and status.
 *
 * An earlier version of the handler papered over that with
 *
 *     `${notifEvent.userId}@goa.app`
 *
 * which is not an address. The project owns no domain, so every notification
 * would have been sent to a nonexistent mailbox on a domain we do not control —
 * and it would have failed silently, because the database row still inserts and
 * GET /notifications still returns it. A notification service whose normal
 * state is "nothing visibly happened" hides that kind of bug indefinitely.
 *
 * GET /users/:id on the User service is guarded by InternalAuthGuard and returns
 * the user with their email, which is what this uses.
 */

const USER_SERVICE_URL = process.env.USER_SERVICE_URL || 'http://user-service:8081';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

export class UserEmailLookupError extends Error {}

export async function lookupUserEmail(userId: string): Promise<string> {
    if (!INTERNAL_API_KEY) {
        throw new UserEmailLookupError(
            'INTERNAL_API_KEY is not set — cannot authenticate to the User service',
        );
    }

    const url = `${USER_SERVICE_URL}/users/${encodeURIComponent(userId)}`;
    let response: Response;
    try {
        response = await fetch(url, {
            headers: { 'X-Internal-API-Key': INTERNAL_API_KEY },
        });
    } catch (cause) {
        throw new UserEmailLookupError(`User service unreachable at ${url}: ${String(cause)}`);
    }

    if (!response.ok) {
        throw new UserEmailLookupError(
            `User service returned ${response.status} for user ${userId}`,
        );
    }

    const body = (await response.json()) as { email?: string };
    if (!body?.email) {
        // Throwing rather than falling back is the point. A thrown error puts
        // this message into batchItemFailures, so SQS retries it and it
        // eventually reaches the DLQ where someone can see it. A fabricated
        // address would send mail into a void and report success.
        throw new UserEmailLookupError(`User ${userId} has no email address`);
    }
    return body.email;
}

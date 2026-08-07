import asyncio
import json
import structlog
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)
from aiobotocore.session import get_session


from app.core.config import settings
from app.services.profile_repo import delete_local_user_data, upsert_local_profiles


logger = structlog.get_logger("rag_service.sqs_consumer")


# ClientError codes that mean "these credentials will never work", as opposed to
# "this queue does not exist yet". Retrying the first kind is an infinite loop;
# retrying the second is the whole point of the backoff below.
_FATAL_CLIENT_ERROR_CODES = frozenset(
    {
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "SignatureDoesNotMatch",
        "AuthFailure",
        "AccessDenied",
        "AccessDeniedException",
    }
)


def _is_unrecoverable_auth_error(exc: Exception) -> bool:
    """True when no amount of waiting will make this call succeed.

    Missing/partial credentials and rejected credentials are configuration
    faults: the process cannot fix them by retrying, so the consumer should
    log once and stop rather than spin until the container is killed.
    """
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError)):
        return True
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code")
        return code in _FATAL_CLIENT_ERROR_CODES
    return False


def parse_user_event(body: str) -> dict:
    event = json.loads(body)
    if event.get("Type") == "Notification" and event.get("Message"):
        return json.loads(event["Message"])
    return event


async def consume_sqs_messages():
    """
    Background task to consume UserUpdated events from SQS.
    """

    session = get_session()
    client_options = {
        "region_name": settings.AWS_REGION,
        "endpoint_url": settings.AWS_ENDPOINT_URL,
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        client_options["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        client_options["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

    async with session.create_client("sqs", **client_options) as sqs_client:
        # Retry rather than return. This lookup runs at startup, and the queue is
        # created by an infrastructure step RAG does not control -- compose only
        # waits for LocalStack's health check, which passes before the user-events
        # topology exists. Giving up on the first NonExistentQueue killed profile
        # replication for the entire life of the process: nothing repopulated
        # local_user_profiles, so /match answered 425 forever and the Opportunities
        # page sat on "Your profile is still syncing" until someone restarted RAG.
        #
        # Retrying is only correct for a condition that can actually resolve on
        # its own. A credential fault cannot: retrying it spins until the task is
        # cancelled, which is an unkillable loop in production and an indefinite
        # hang in any test that drives this function to completion.
        backoff = 5
        while True:
            try:
                response = await sqs_client.get_queue_url(QueueName=settings.SQS_QUEUE_NAME)
                queue_url = response["QueueUrl"]
                logger.info("SQS Consumer connected", queue_url=queue_url)
                break
            except asyncio.CancelledError:
                logger.info("SQS consumer cancelled before connecting")
                return
            except (BotoCoreError, ClientError) as e:
                if _is_unrecoverable_auth_error(e):
                    logger.error(
                        "SQS credentials missing or rejected; consumer stopping",
                        error=str(e),
                        queue_name=settings.SQS_QUEUE_NAME,
                    )
                    return
                logger.error(
                    "Failed to get SQS queue URL; retrying",
                    error=str(e),
                    queue_name=settings.SQS_QUEUE_NAME,
                    retry_in_seconds=backoff,
                )
                await asyncio.sleep(backoff)
                # Capped so a permanently misconfigured queue name costs one log
                # line a minute rather than a tight loop against SQS.
                backoff = min(backoff * 2, 60)

        while True:
            try:
                # Long polling setup (20s) to minimize empty receive requests
                response = await sqs_client.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=20,
                )

                if "Messages" in response:
                    for msg in response["Messages"]:
                        try:
                            # Parse the incoming event
                            body = parse_user_event(msg["Body"])

                            # Ensure it's the event we care about
                            if body.get('type') == 'account.deleted':
                                payload = body.get('payload', {})
                                await delete_local_user_data(payload['userId'])
                                logger.info(
                                    "Processed AccountDeleted event",
                                    user_id=payload.get("userId"),
                                    event_timestamp=body.get("timestamp"),
                                )
                            elif body.get('type') == 'user.updated':
                                payload = body.get('payload', {})
                                # Pass the envelope timestamp for out-of-order protection
                                payload['last_synced_at'] = body.get('timestamp')
                                
                                # Fire it into our shared DB upsert logic!
                                await upsert_local_profiles(payload)

                                # hook up to Prometheus later
                                logger.info(
                                    "Processed UserUpdated event",
                                    user_id=payload.get("userId"),
                                    event_timestamp=body.get("timestamp"),
                                )

                            await sqs_client.delete_message(
                                QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"]
                            )
                        except Exception as process_err:
                            logger.error(
                                "Error processing SQS message", error=str(process_err)
                            )

            except asyncio.CancelledError:
                logger.info("SQS consumer task cancelled, shutting down gracefully")
                break
            except Exception as e:
                logger.error("Error receiving SQS messages", error=str(e))
                await asyncio.sleep(5)


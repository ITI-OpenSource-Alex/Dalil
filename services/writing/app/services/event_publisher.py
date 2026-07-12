from datetime import datetime, timezone

from contracts.events import CVUploaded, CVUploadedPayload


def publish_cv_uploaded(
    sqs_client,
    queue_url: str,
    user_id: str,
    s3_key: str,
    file_name: str,
    correlation_id: str,
) -> None:
    if not queue_url:
        raise RuntimeError("CV_UPLOADED_QUEUE_URL is not configured")

    event = CVUploaded(
        timestamp=datetime.now(timezone.utc),
        correlationId=correlation_id,
        payload=CVUploadedPayload(
            userId=user_id,
            s3Key=s3_key,
            fileName=file_name,
        ),
    )
    if hasattr(event, "model_dump_json"):
        message_body = event.model_dump_json()
    else:
        message_body = event.json()

    sqs_client.send_message(QueueUrl=queue_url, MessageBody=message_body)

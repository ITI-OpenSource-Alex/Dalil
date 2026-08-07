import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
from botocore.exceptions import ClientError, NoCredentialsError
from app.services.sqs_consumer import consume_sqs_messages


@pytest.mark.asyncio
async def test_sqs_consumer_happy_path(monkeypatch):
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.return_value = {"QueueUrl": "http://mock-queue-url"}

    mock_message = {
        "MessageId": "msg-123",
        "ReceiptHandle": "rh-123",
        "Body": json.dumps({
            "type": "user.updated",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": {"userId": "user-123", "gpa": 3.8}
        })
    }

    mock_sqs_client.receive_message.side_effect = [
        {"Messages": [mock_message]},
        Exception("Simulate network error"),
    ]

    mock_upsert = AsyncMock()
    monkeypatch.setattr("app.services.sqs_consumer.upsert_local_profiles", mock_upsert)

    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError("Break loop"))
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_upsert.assert_called_once_with({"userId": "user-123", "gpa": 3.8, "last_synced_at": "2024-01-01T00:00:00Z"})
    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="http://mock-queue-url", ReceiptHandle="rh-123"
    )


@pytest.mark.asyncio
async def test_sqs_consumer_ignored_event(monkeypatch):
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.return_value = {"QueueUrl": "http://mock-queue-url"}

    mock_message = {
        "MessageId": "msg-123",
        "ReceiptHandle": "rh-123",
        "Body": json.dumps({"type": "user.deleted", "payload": {"userId": "user-123"}}),
    }

    mock_sqs_client.receive_message.side_effect = [
        {"Messages": [mock_message]},
        Exception("Simulate network error"),
    ]

    mock_upsert = AsyncMock()
    monkeypatch.setattr("app.services.sqs_consumer.upsert_local_profiles", mock_upsert)

    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError("Break loop"))
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_upsert.assert_not_called()
    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="http://mock-queue-url", ReceiptHandle="rh-123"
    )


@pytest.mark.asyncio
async def test_sqs_consumer_upsert_failure_nacks(monkeypatch):
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.return_value = {"QueueUrl": "http://mock-queue-url"}

    mock_message = {
        "MessageId": "msg-123",
        "ReceiptHandle": "rh-123",
        "Body": json.dumps({"type": "user.updated", "payload": {"userId": "user-123"}}),
    }

    mock_sqs_client.receive_message.side_effect = [
        {"Messages": [mock_message]},
        Exception("Simulate network error"),
    ]

    mock_upsert = AsyncMock(side_effect=Exception("DB Error"))
    monkeypatch.setattr("app.services.sqs_consumer.upsert_local_profiles", mock_upsert)

    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError("Break loop"))
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_upsert.assert_called_once()
    mock_sqs_client.delete_message.assert_not_called()


@pytest.mark.asyncio
async def test_sqs_consumer_stops_cleanly_without_aws_credentials():
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.side_effect = NoCredentialsError()

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_sqs_client.receive_message.assert_not_called()


@pytest.mark.asyncio
async def test_sqs_consumer_retries_a_queue_that_does_not_exist_yet(monkeypatch):
    """The other half of the credential fix, and the reason it is narrow.

    A missing queue is transient: compose's LocalStack health check passes
    before the user-events topology is created, so the first lookup on a cold
    start legitimately fails and must be retried. Returning here instead would
    restore the original defect -- profile replication dead for the life of the
    process, /match answering 425 forever.

    Only unrecoverable *auth* faults stop the consumer; everything else keeps
    backing off. asyncio.sleep is patched out so the backoff costs no wall time.
    """
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.side_effect = [
        ClientError(
            {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}},
            "GetQueueUrl",
        ),
        {"QueueUrl": "http://mock-queue-url"},
    ]
    # Stop after the queue resolves so the receive loop does not run forever.
    mock_sqs_client.receive_message.side_effect = asyncio.CancelledError("Break loop")

    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    # Retried past the missing queue rather than giving up on it.
    assert mock_sqs_client.get_queue_url.await_count == 2
    mock_sqs_client.receive_message.assert_awaited()


@pytest.mark.asyncio
async def test_sqs_consumer_stops_on_rejected_credentials():
    """A ClientError can also be terminal. Bad keys produce InvalidClientTokenId
    rather than NoCredentialsError, and retrying those spins just as forever."""
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.side_effect = ClientError(
        {"Error": {"Code": "InvalidClientTokenId"}}, "GetQueueUrl"
    )

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_sqs_client.receive_message.assert_not_called()


@pytest.mark.asyncio
async def test_sqs_consumer_account_deleted_purges_local_data(monkeypatch):
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.return_value = {"QueueUrl": "http://mock-queue-url"}

    mock_message = {
        "MessageId": "msg-123",
        "ReceiptHandle": "rh-123",
        "Body": json.dumps({"type": "account.deleted", "payload": {"userId": "user-123"}}),
    }

    mock_sqs_client.receive_message.side_effect = [
        {"Messages": [mock_message]},
        Exception("Simulate network error"),
    ]

    mock_delete = AsyncMock()
    monkeypatch.setattr("app.services.sqs_consumer.delete_local_user_data", mock_delete)
    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError("Break loop"))
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_delete.assert_awaited_once_with("user-123")
    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="http://mock-queue-url", ReceiptHandle="rh-123"
    )


@pytest.mark.asyncio
async def test_sqs_consumer_account_deleted_purges_local_data_from_sns_envelope(monkeypatch):
    mock_sqs_client = AsyncMock()
    mock_sqs_client.get_queue_url.return_value = {"QueueUrl": "http://mock-queue-url"}

    event = {"type": "account.deleted", "payload": {"userId": "user-123"}}
    mock_message = {
        "MessageId": "msg-123",
        "ReceiptHandle": "rh-123",
        "Body": json.dumps({
            "Type": "Notification",
            "Message": json.dumps(event),
        }),
    }

    mock_sqs_client.receive_message.side_effect = [
        {"Messages": [mock_message]},
        Exception("Simulate network error"),
    ]

    mock_delete = AsyncMock()
    monkeypatch.setattr("app.services.sqs_consumer.delete_local_user_data", mock_delete)
    mock_sleep = AsyncMock(side_effect=asyncio.CancelledError("Break loop"))
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    with patch("app.services.sqs_consumer.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_sqs_client)
        mock_client_ctx.__aexit__ = AsyncMock()
        mock_session.create_client.return_value = mock_client_ctx
        mock_get_session.return_value = mock_session

        await consume_sqs_messages()

    mock_delete.assert_awaited_once_with("user-123")
    mock_sqs_client.delete_message.assert_called_once_with(
        QueueUrl="http://mock-queue-url", ReceiptHandle="rh-123"
    )

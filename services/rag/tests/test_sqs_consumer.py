import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
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
